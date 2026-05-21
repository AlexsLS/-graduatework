import sys
import time
import os
from collections import defaultdict, deque


class BitWriter:
    def __init__(self):
        self.buf = bytearray()
        self.acc = 0
        self.n = 0
        self.total_bits = 0

    def write_bits(self, value: int, length: int):
        if length == 0:
            return
        self.total_bits += length
        while length > 0:
            free = 64 - self.n
            to_write = min(free, length)
            shift = length - to_write
            chunk = (value >> shift) & ((1 << to_write) - 1)
            self.acc = (self.acc << to_write) | chunk
            self.n += to_write
            length -= to_write
            if self.n >= 8:
                while self.n >= 8:
                    byte = (self.acc >> (self.n - 8)) & 0xFF
                    self.buf.append(byte)
                    self.n -= 8
                if self.n == 0:
                    self.acc = 0
                else:
                    self.acc &= (1 << self.n) - 1

    def flush(self):
        if self.n > 0:
            self.acc <<= (8 - self.n)
            self.buf.append(self.acc & 0xFF)
            self.acc = 0
            self.n = 0

    def get_bytes(self):
        return bytes(self.buf)


class BitReader:
    def __init__(self, data: bytes, bit_length: int = None):
        self.data = data
        self.byte_pos = 0
        self.acc = 0
        self.n = 0
        self.total_bits = len(data) * 8 if bit_length is None else bit_length
        self.read_bits_count = 0

    def _fill(self):
        if self.n == 0 and self.byte_pos < len(self.data):
            self.acc = self.data[self.byte_pos]
            self.byte_pos += 1
            self.n = 8

    def read_bit(self):
        if self.read_bits_count >= self.total_bits:
            return None
        self._fill()
        if self.n == 0:
            return None
        bit = (self.acc >> (self.n - 1)) & 1
        self.n -= 1
        self.read_bits_count += 1
        return bit

    def read_bits(self, length):
        if length == 0:
            return 0
        val = 0
        for _ in range(length):
            b = self.read_bit()
            if b is None:
                return None
            val = (val << 1) | b
        return val


class AHNode:
    __slots__ = ("symbol", "weight", "parent", "left", "right", "order", "is_nyt")
    def __init__(self, symbol=None, weight=0, parent=None, left=None, right=None, order=0, is_nyt=False):
        self.symbol = symbol
        self.weight = weight
        self.parent = parent
        self.left = left
        self.right = right
        self.order = order
        self.is_nyt = is_nyt

    def is_leaf(self):
        return self.left is None and self.right is None


class AdaptiveHuffman:
    def __init__(self):
        self.max_order = 512
        self.root = AHNode(is_nyt=True, order=self.max_order)
        self.nyt = self.root
        self.nodes_by_symbol = {}
        self.blocks = defaultdict(deque)
        self.blocks[0].append(self.root)

    def _add_new_symbol(self, symbol):
        old_nyt = self.nyt
        internal = AHNode(symbol=None, weight=0, order=old_nyt.order, parent=old_nyt.parent)
        right_order = old_nyt.order - 1
        left_order = old_nyt.order - 2
        new_nyt = AHNode(symbol=None, weight=0, order=left_order, parent=internal, is_nyt=True)
        leaf = AHNode(symbol=symbol, weight=0, order=right_order, parent=internal)
        internal.left = new_nyt
        internal.right = leaf
        if old_nyt.parent is None:
            self.root = internal
            internal.parent = None
        else:
            if old_nyt.parent.left is old_nyt:
                old_nyt.parent.left = internal
            else:
                old_nyt.parent.right = internal
            internal.parent = old_nyt.parent
        self.nyt = new_nyt
        try:
            self.blocks[0].remove(old_nyt)
        except ValueError:
            pass
        self.blocks[0].append(internal)
        self.blocks[0].append(leaf)
        self.blocks[0].append(new_nyt)
        self.nodes_by_symbol[symbol] = leaf
        return leaf

    def _swap_nodes(self, a: AHNode, b: AHNode):
        if a is b or a.parent is b or b.parent is a:
            return
        pa, pb = a.parent, b.parent
        if pa.left is a:
            pa.left = b
        else:
            pa.right = b
        if pb.left is b:
            pb.left = a
        else:
            pb.right = a
        a.parent, b.parent = pb, pa
        a.order, b.order = b.order, a.order

    def _update_blocks_on_weight_change(self, node, old_w, new_w):
        if old_w in self.blocks:
            try:
                self.blocks[old_w].remove(node)
                if not self.blocks[old_w]:
                    del self.blocks[old_w]
            except ValueError:
                pass
        self.blocks[new_w].append(node)

    def _increment_weight(self, node):
        while node is not None:
            w = node.weight
            leader = None
            dq = self.blocks.get(w)
            if dq:
                for cand in reversed(dq):
                    if cand is not node and cand.order > node.order:
                        leader = cand
                        break
            if leader is not None and leader is not node and leader is not node.parent:
                self._swap_nodes(node, leader)
            old_w = node.weight
            node.weight += 1
            self._update_blocks_on_weight_change(node, old_w, node.weight)
            node = node.parent

    def _get_path_bits(self, node):
        bits = 0
        length = 0
        cur = node
        while cur.parent is not None:
            if cur.parent.right is cur:
                bits |= (1 << length)
            length += 1
            cur = cur.parent
        val = 0
        for i in range(length):
            val = (val << 1) | ((bits >> (length - 1 - i)) & 1)
        return val, length

    def get_code_for_symbol(self, symbol):
        if symbol in self.nodes_by_symbol:
            return self._get_path_bits(self.nodes_by_symbol[symbol])
        else:
            return self._get_path_bits(self.nyt)

    def feed_symbol_without_output(self, symbol):
        if symbol in self.nodes_by_symbol:
            node = self.nodes_by_symbol[symbol]
            self._increment_weight(node)
        else:
            leaf = self._add_new_symbol(symbol)
            self._increment_weight(leaf)


def compress_with_window(input_file, output_file, window_size=1024, rebuild_interval=1024):
    with open(input_file, "rb") as f:
        data = f.read()

    if not data:
        with open(output_file, "wb") as f:
            f.write((0).to_bytes(4, "big"))
            f.write((window_size).to_bytes(4, "big"))
            f.write((rebuild_interval).to_bytes(4, "big"))
        return

    window = deque(maxlen=window_size)
    ah = AdaptiveHuffman()
    writer = BitWriter()
    counter_since_rebuild = 0

    for b in data:
        if b in ah.nodes_by_symbol:
            val, length = ah.get_code_for_symbol(b)
            if length > 0:
                writer.write_bits(val, length)
            ah._increment_weight(ah.nodes_by_symbol[b])
        else:
            val, length = ah.get_code_for_symbol(None)
            if length > 0:
                writer.write_bits(val, length)
            writer.write_bits(b, 8)
            leaf = ah._add_new_symbol(b)
            ah._increment_weight(leaf)

        if len(window) == window_size:
            window.popleft()
        window.append(b)

        counter_since_rebuild += 1
        if counter_since_rebuild >= rebuild_interval:
            ah = AdaptiveHuffman()
            for wb in window:
                ah.feed_symbol_without_output(wb)
            counter_since_rebuild = 0

    writer.flush()
    compressed = writer.get_bytes()
    bit_length = writer.total_bits

    with open(output_file, "wb") as f:
        f.write(bit_length.to_bytes(4, "big"))
        f.write(window_size.to_bytes(4, "big"))
        f.write(rebuild_interval.to_bytes(4, "big"))
        f.write(compressed)


def decompress_with_window(input_file, output_file):
    with open(input_file, "rb") as f:
        bit_length = int.from_bytes(f.read(4), "big")
        window_size = int.from_bytes(f.read(4), "big")
        rebuild_interval = int.from_bytes(f.read(4), "big")
        compressed = f.read()

    reader = BitReader(compressed, bit_length)
    window = deque(maxlen=window_size)
    ah = AdaptiveHuffman()
    out = bytearray()
    counter_since_rebuild = 0

    while True:
        if ah.root.is_leaf() and ah.root.is_nyt:
            val = reader.read_bits(8)
            if val is None:
                break
            out.append(val)
            ah._add_new_symbol(val)
            ah._increment_weight(ah.nodes_by_symbol[val])
            if len(window) == window_size:
                window.popleft()
            window.append(val)
            counter_since_rebuild += 1
            if counter_since_rebuild >= rebuild_interval:
                ah = AdaptiveHuffman()
                for wb in window:
                    ah.feed_symbol_without_output(wb)
                counter_since_rebuild = 0
            continue

        node = ah.root
        while not node.is_leaf():
            b = reader.read_bit()
            if b is None:
                with open(output_file, "wb") as f:
                    f.write(out)
                return
            node = node.right if b == 1 else node.left

        if node.is_nyt:
            val = reader.read_bits(8)
            if val is None:
                break
            out.append(val)
            ah._add_new_symbol(val)
            ah._increment_weight(ah.nodes_by_symbol[val])
        else:
            sym = node.symbol
            out.append(sym)
            ah._increment_weight(node)

        if len(window) == window_size:
            window.popleft()
        window.append(out[-1])

        counter_since_rebuild += 1
        if counter_since_rebuild >= rebuild_interval:
            ah = AdaptiveHuffman()
            for wb in window:
                ah.feed_symbol_without_output(wb)
            counter_since_rebuild = 0

    with open(output_file, "wb") as f:
        f.write(out)


def main():
    if len(sys.argv) < 2:
        print("Usage: python adaptive_sliding_huffman.py <input_file> [window_size] [rebuild_interval]")
        sys.exit(1)

    input_file = sys.argv[1]
    window_size = int(sys.argv[2]) if len(sys.argv) > 2 else 4096
    rebuild_interval = int(sys.argv[3]) if len(sys.argv) > 3 else 1024

    compressed_file = "compressed_window_adaptive.huff"
    decompressed_file = "decompressed_window_adaptive.bin"

    # --- Sizes ---
    input_size = os.path.getsize(input_file)

    # --- Compress ---
    t1 = time.time()
    compress_with_window(input_file, compressed_file, window_size, rebuild_interval)
    t2 = time.time()

    compressed_size = os.path.getsize(compressed_file)

    # --- Decompress ---
    t3 = time.time()
    decompress_with_window(compressed_file, decompressed_file)
    t4 = time.time()

    # --- Check correctness ---
    with open(input_file, "rb") as f1, open(decompressed_file, "rb") as f2:
        ok = (f1.read() == f2.read())

    # --- Print results ---
    print("\n===== ADAPTIVE HUFFMAN =====")
    print(f"Window size:       {window_size}")
    print(f"Rebuild interval:  {rebuild_interval}")
    print(f"Input size:        {input_size} bytes")
    print(f"Compressed size:   {compressed_size} bytes")
    print(f"Compression ratio: {compressed_size / input_size:.3f}")
    print(f"Compress time:     {t2 - t1:.4f} sec")
    print(f"Decompress time:   {t4 - t3:.4f} sec")
    print(f"Correct decode:    {ok}")

if __name__ == "__main__":
    main()
