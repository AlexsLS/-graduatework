import sys
import time
import os
from collections import deque, defaultdict

# =========================
#   Bit I/O
# =========================

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
            free = 8 - self.n
            to_write = min(free, length)
            shift = length - to_write
            chunk = (value >> shift) & ((1 << to_write) - 1)
            self.acc = (self.acc << to_write) | chunk
            self.n += to_write
            length -= to_write
            if self.n == 8:
                self.buf.append(self.acc & 0xFF)
                self.acc = 0
                self.n = 0

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
        if length == 0:
            return 0
        val = 0
        for _ in range(length):
            b = self.read_bit()
            if b is None:
                return None
            val = (val << 1) | b
        return val


# =========================
#   Vitter Node
# =========================

class VNode:
    __slots__ = ("symbol", "weight", "parent", "left", "right", "order", "is_nyt")

    def __init__(self, symbol=None, weight=0, parent=None,
                 left=None, right=None, order=0, is_nyt=False):
        self.symbol = symbol
        self.weight = weight
        self.parent = parent
        self.left = left
        self.right = right
        self.order = order
        self.is_nyt = is_nyt

    def is_leaf(self):
        return self.left is None and self.right is None


# =========================
#   Adaptive Huffman Vitter + Honest Window
# =========================

class AdaptiveHuffmanVitterWindow:
    """
    Адаптивный Хаффман по Vitter (Algorithm V) + честное окно:
    - при входе символа в окно: weight++
    - при выходе символа из окна: weight--
    - дерево поддерживает sibling property (Vitter)
    """

    def __init__(self, max_symbols=256):
        # максимальное количество различных символов
        self.max_symbols = max_symbols
        # максимальный порядок (номер) узла
        self.max_order = 2 * max_symbols - 1

        # корень = NYT
        self.root = VNode(is_nyt=True, order=self.max_order)
        self.nyt = self.root

        # символ -> лист
        self.leaf_for_symbol = {}

        # блоки по весу: weight -> список узлов (в порядке возрастания order)
        self.blocks = defaultdict(list)
        self.blocks[0].append(self.root)

    # ---------- вспомогательные ----------

    def _is_ancestor(self, a: VNode, b: VNode) -> bool:
        cur = b.parent
        while cur is not None:
            if cur is a:
                return True
            cur = cur.parent
        return False

    def _swap_nodes(self, a: VNode, b: VNode):
        if a is b:
            return
        if self._is_ancestor(a, b) or self._is_ancestor(b, a):
            return

        pa, pb = a.parent, b.parent
        if pa is None or pb is None:
            # корень не должен меняться местами с потомком
            if pa is None and pb is None:
                return
            if pa is None and self._is_ancestor(a, b):
                return
            if pb is None and self._is_ancestor(b, a):
                return

        if pa is not None:
            if pa.left is a:
                pa.left = b
            else:
                pa.right = b
        else:
            self.root = b

        if pb is not None:
            if pb.left is b:
                pb.left = a
            else:
                pb.right = a
        else:
            self.root = a

        a.parent, b.parent = pb, pa
        a.order, b.order = b.order, a.order

    def _remove_from_block(self, node: VNode, w: int):
        lst = self.blocks.get(w)
        if not lst:
            return
        try:
            lst.remove(node)
            if not lst:
                del self.blocks[w]
        except ValueError:
            pass

    def _add_to_block(self, node: VNode, w: int):
        lst = self.blocks[w]
        # вставляем по order (возрастающий)
        # для ускорения можно просто append, но тогда поиск лидера будет чуть дороже
        # здесь делаем простой вставкой в конец
        lst.append(node)

    def _block_leader_for_weight(self, w: int, min_order: int = -1) -> VNode | None:
        """
        Возвращает узел с максимальным order среди узлов веса w,
        у которого order > min_order.
        """
        lst = self.blocks.get(w)
        if not lst:
            return None
        leader = None
        best_order = min_order
        for node in lst:
            if node.order > best_order:
                best_order = node.order
                leader = node
        return leader

    # ---------- построение пути ----------

    def _get_code_for_node(self, node: VNode):
        bits = 0
        length = 0
        cur = node
        while cur.parent is not None:
            if cur.parent.right is cur:
                bits |= (1 << length)
            length += 1
            cur = cur.parent
        # реверс битов
        val = 0
        for i in range(length):
            val = (val << 1) | ((bits >> (length - 1 - i)) & 1)
        return val, length

    def get_code_for_symbol(self, symbol: int):
        if symbol in self.leaf_for_symbol:
            return self._get_code_for_node(self.leaf_for_symbol[symbol])
        else:
            # код NYT
            return self._get_code_for_node(self.nyt)

    # ---------- добавление нового символа ----------

    def _add_new_symbol(self, symbol: int) -> VNode:
        old_nyt = self.nyt
        # внутренний узел вместо старого NYT
        internal = VNode(symbol=None, weight=0, parent=old_nyt.parent,
                         order=old_nyt.order, is_nyt=False)
        # новый NYT и лист для символа
        right_order = old_nyt.order - 1
        left_order = old_nyt.order - 2
        new_nyt = VNode(symbol=None, weight=0, parent=internal,
                        order=left_order, is_nyt=True)
        leaf = VNode(symbol=symbol, weight=0, parent=internal,
                     order=right_order, is_nyt=False)
        internal.left = new_nyt
        internal.right = leaf

        if old_nyt.parent is None:
            self.root = internal
        else:
            if old_nyt.parent.left is old_nyt:
                old_nyt.parent.left = internal
            else:
                old_nyt.parent.right = internal

        self.nyt = new_nyt
        self.leaf_for_symbol[symbol] = leaf

        # обновляем блоки: старый NYT был в weight=0
        self._remove_from_block(old_nyt, 0)
        self._add_to_block(internal, 0)
        self._add_to_block(leaf, 0)
        self._add_to_block(new_nyt, 0)

        return leaf

    # ---------- инкремент веса (Vitter) ----------

    def _increment(self, node: VNode):
        while node is not None:
            w = node.weight
            # лидер блока веса w с order > node.order
            leader = self._block_leader_for_weight(w, min_order=node.order)
            if leader is not None and leader is not node and leader is not node.parent:
                self._swap_nodes(node, leader)

            self._remove_from_block(node, w)
            node.weight = w + 1
            self._add_to_block(node, node.weight)

            node = node.parent

    # ---------- декремент веса (честное окно) ----------

    def _decrement(self, node: VNode):
        while node is not None:
            w = node.weight
            if w == 0:
                # ниже нуля не идём
                return
            # для декремента: ищем узел с тем же весом, но меньшим order
            lst = self.blocks.get(w)
            leader = None
            if lst:
                for cand in lst:
                    if cand is not node and cand.order < node.order:
                        leader = cand
                        break
            if leader is not None and leader is not node and leader is not node.parent:
                self._swap_nodes(node, leader)

            self._remove_from_block(node, w)
            node.weight = w - 1
            self._add_to_block(node, node.weight)

            node = node.parent

    # ---------- публичные методы ----------

    def encode_symbol(self, symbol: int):
        """
        Возвращает (value, length) кода для символа.
        Если символ новый — код NYT.
        """
        return self.get_code_for_symbol(symbol)

    def update_on_insert(self, symbol: int):
        """
        Обновление дерева при входе символа в окно (weight++).
        """
        if symbol in self.leaf_for_symbol:
            node = self.leaf_for_symbol[symbol]
        else:
            node = self._add_new_symbol(symbol)
        self._increment(node)

    def update_on_remove(self, symbol: int):
        """
        Обновление дерева при выходе символа из окна (weight--).
        """
        node = self.leaf_for_symbol.get(symbol)
        if node is None:
            return
        self._decrement(node)


# =========================
#   Compress / Decompress with Honest Window
# =========================

def compress_vitter_window(input_file, output_file, window_size=4096):
    with open(input_file, "rb") as f:
        data = f.read()

    if not data:
        with open(output_file, "wb") as f:
            f.write((0).to_bytes(4, "big"))
            f.write(window_size.to_bytes(4, "big"))
        return

    ah = AdaptiveHuffmanVitterWindow()
    writer = BitWriter()
    window = deque(maxlen=window_size)

    for b in data:
        # код символа
        val, length = ah.encode_symbol(b)
        if length > 0:
            writer.write_bits(val, length)

        # если символ новый — пишем его байт явно
        if b not in ah.leaf_for_symbol:
            writer.write_bits(b, 8)

        # честное окно: вход
        ah.update_on_insert(b)

        # честное окно: выход
        if len(window) == window_size:
            old = window.popleft()
            ah.update_on_remove(old)

        window.append(b)

    writer.flush()
    compressed = writer.get_bytes()
    bit_length = writer.total_bits

    with open(output_file, "wb") as f:
        f.write(bit_length.to_bytes(4, "big"))
        f.write(window_size.to_bytes(4, "big"))
        f.write(compressed)


def decompress_vitter_window(input_file, output_file):
    with open(input_file, "rb") as f:
        bit_length = int.from_bytes(f.read(4), "big")
        window_size = int.from_bytes(f.read(4), "big")
        compressed = f.read()

    reader = BitReader(compressed, bit_length)
    ah = AdaptiveHuffmanVitterWindow()
    window = deque(maxlen=window_size)
    out = bytearray()

    while True:
        # если дерево только NYT
        if ah.root.is_leaf() and ah.root.is_nyt:
            val = reader.read_bits(8)
            if val is None:
                break
            out.append(val)
            ah.update_on_insert(val)
            if len(window) == window_size:
                old = window.popleft()
                ah.update_on_remove(old)
            window.append(val)
            continue

        # спускаемся по дереву
        node = ah.root
        while not node.is_leaf():
            bit = reader.read_bit()
            if bit is None:
                with open(output_file, "wb") as f:
                    f.write(out)
                return
            node = node.right if bit == 1 else node.left

        if node.is_nyt:
            val = reader.read_bits(8)
            if val is None:
                break
            out.append(val)
            ah.update_on_insert(val)
        else:
            sym = node.symbol
            out.append(sym)
            ah.update_on_insert(sym)

        if len(window) == window_size:
            old = window.popleft()
            ah.update_on_remove(old)
        window.append(out[-1])

    with open(output_file, "wb") as f:
        f.write(out)


# =========================
#   main + stats
# =========================

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "input.txt"
    compressed_file = "compressed_vitter_window.huff"
    decompressed_file = "decompressed_vitter_window.bin"
    window_size = 1024

    input_size = os.path.getsize(input_file)

    t1 = time.time()
    compress_vitter_window(input_file, compressed_file, window_size)
    t2 = time.time()

    compressed_size = os.path.getsize(compressed_file)

    t3 = time.time()
    decompress_vitter_window(compressed_file, decompressed_file)
    t4 = time.time()

    with open(input_file, "rb") as f1, open(decompressed_file, "rb") as f2:
        ok = (f1.read() == f2.read())

    print("\n===== VITTER ADAPTIVE HUFFMAN (HONEST WINDOW) =====")
    print(f"Window size:       {window_size}")
    print(f"Input size:        {input_size} bytes")
    print(f"Compressed size:   {compressed_size} bytes")
    print(f"Compression ratio: {compressed_size / input_size:.3f}")
    print(f"Compress time:     {t2 - t1:.4f} sec")
    print(f"Decompress time:   {t4 - t3:.4f} sec")
    print(f"Correct decode:    {ok}")


if __name__ == "__main__":
    main()
