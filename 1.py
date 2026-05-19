import sys
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
    def __init__(self, data: bytes, bit_length: int):
        self.data = data
        self.byte_pos = 0
        self.acc = 0
        self.n = 0
        self.total_bits = bit_length
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


class AdaptiveHuffmanFGK:
    def __init__(self):
        self.max_order = 512
        self.root = AHNode(is_nyt=True, order=self.max_order)
        self.nyt = self.root
        self.nodes_by_symbol = {}
        self.blocks = defaultdict(deque)
        self.blocks[0].append(self.root)

    def _add_new_symbol(self, symbol):
        old = self.nyt
        internal = AHNode(order=old.order, parent=old.parent)
        left = AHNode(order=old.order - 2, parent=internal, is_nyt=True)
        right = AHNode(symbol=symbol, order=old.order - 1, parent=internal)

        internal.left = left
        internal.right = right

        if old.parent is None:
            self.root = internal
        else:
            if old.parent.left is old:
                old.parent.left = internal
            else:
                old.parent.right = internal

        self.nyt = left
        self.nodes_by_symbol[symbol] = right

        try:
            self.blocks[0].remove(old)
            if not self.blocks[0]:
                del self.blocks[0]
        except:
            pass

        # порядок: сначала NYT, потом новый символ, потом внутренний
        self.blocks[0].append(internal)
        self.blocks[0].append(right)
        self.blocks[0].append(left)

        return right

    def _is_ancestor(self, a, b):
        cur = b.parent
        while cur is not None:
            if cur is a:
                return True
            cur = cur.parent
        return False

    def _swap(self, a, b):
        if a is b:
            return
        # нельзя менять местами предка и потомка
        if self._is_ancestor(a, b) or self._is_ancestor(b, a):
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

    def _update_blocks(self, node, old_w, new_w):
        try:
            self.blocks[old_w].remove(node)
            if not self.blocks[old_w]:
                del self.blocks[old_w]
        except:
            pass
        self.blocks[new_w].append(node)

    def _increment(self, node):
        while node is not None:
            w = node.weight
            leader = None
            dq = self.blocks.get(w)
            if dq:
                for cand in reversed(dq):
                    if cand is not node and cand.order > node.order:
                        leader = cand
                        break
            if leader and leader is not node.parent:
                self._swap(node, leader)
            old_w = node.weight
            node.weight += 1
            self._update_blocks(node, old_w, node.weight)
            node = node.parent

    def _path(self, node):
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

    def encode_symbol(self, symbol):
        if symbol in self.nodes_by_symbol:
            return self._path(self.nodes_by_symbol[symbol])
        else:
            return self._path(self.nyt)

    def update(self, symbol):
        if symbol in self.nodes_by_symbol:
            node = self.nodes_by_symbol[symbol]
            self._increment(node)
        else:
            leaf = self._add_new_symbol(symbol)
            self._increment(leaf)


def compress_fgk(input_file, output_file):
    with open(input_file, "rb") as f:
        data = f.read()

    ah = AdaptiveHuffmanFGK()
    bw = BitWriter()

    for b in data:
        val, length = ah.encode_symbol(b)
        if length > 0:
            bw.write_bits(val, length)
        if b not in ah.nodes_by_symbol:
            bw.write_bits(b, 8)
        ah.update(b)

    bw.flush()
    out = bw.get_bytes()

    with open(output_file, "wb") as f:
        f.write(bw.total_bits.to_bytes(4, "big"))
        f.write(out)


def decompress_fgk(input_file, output_file):
    with open(input_file, "rb") as f:
        bit_length = int.from_bytes(f.read(4), "big")
        data = f.read()

    br = BitReader(data, bit_length)
    ah = AdaptiveHuffmanFGK()
    out = bytearray()

    while True:
        if ah.root.is_leaf() and ah.root.is_nyt:
            val = br.read_bits(8)
            if val is None:
                break
            out.append(val)
            ah.update(val)
            continue

        node = ah.root
        while not node.is_leaf():
            b = br.read_bit()
            if b is None:
                with open(output_file, "wb") as f:
                    f.write(out)
                return
            node = node.right if b == 1 else node.left

        if node.is_nyt:
            val = br.read_bits(8)
            if val is None:
                break
            out.append(val)
            ah.update(val)
        else:
            out.append(node.symbol)
            ah.update(node.symbol)

    with open(output_file, "wb") as f:
        f.write(out)


def main():
    if len(sys.argv) < 2:
        print("Usage: python fgk_huffman.py <input_file>")
        sys.exit(1)

    input_file = sys.argv[1]

    compressed_file = "compressed_fgk.huff"
    decompressed_file = "decompressed_fgk.bin"

    print(f"Compressing {input_file} -> {compressed_file} ...")
    compress_fgk(input_file, compressed_file)
    print("Decompressing back ...")
    decompress_fgk(compressed_file, decompressed_file)

    with open(input_file, "rb") as f1, open(decompressed_file, "rb") as f2:
        a = f1.read()
        b = f2.read()
        if a == b:
            print("✓ Decompression successful")
        else:
            print("✗ Decompression failed")


if __name__ == "__main__":
    main()
