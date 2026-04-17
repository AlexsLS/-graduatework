import heapq
from collections import Counter, deque
import pickle
import sys
import os

# ====================== Классы и утилиты ======================

class Node:
    def __init__(self, char=None, freq=0, left=None, right=None):
        # char хранится как int (0..255) для байтов, None для внутренних узлов
        self.char = char
        self.freq = freq
        self.left = left
        self.right = right

    def __lt__(self, other):
        # сравнение по частоте для heapq
        return self.freq < other.freq

def build_huffman_tree(frequencies):
    """Построение дерева Хаффмана по текущим частотам (frequencies: Counter[int])"""
    if not frequencies:
        return None
    heap = [Node(char, freq) for char, freq in frequencies.items() if freq > 0]
    if not heap:
        return None
    heapq.heapify(heap)

    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        parent = Node(None, left.freq + right.freq, left, right)
        heapq.heappush(heap, parent)

    return heap[0]

def generate_codes(root, current_code="", codes=None):
    """Генерация кодов из дерева. Возвращает dict: int -> str (битовая строка)"""
    if codes is None:
        codes = {}
    if root is None:
        return codes
    if root.char is not None:
        # Если дерево состоит из одного листа, current_code может быть пустым — назначаем ненулевой код
        codes[root.char] = current_code if current_code != "" else "0"
        return codes
    generate_codes(root.left, current_code + "0", codes)
    generate_codes(root.right, current_code + "1", codes)
    return codes

class BitWriter:
    """Буфер для записи битов и получения байтов"""
    def __init__(self):
        self.bytes = bytearray()
        self.current = 0
        self.nbits = 0  # сколько битов записано в current (0..7)
        self.total_bits = 0

    def write_bits(self, bits: str):
        for b in bits:
            self.current = (self.current << 1) | (1 if b == '1' else 0)
            self.nbits += 1
            self.total_bits += 1
            if self.nbits == 8:
                self.bytes.append(self.current)
                self.current = 0
                self.nbits = 0

    def flush(self):
        if self.nbits > 0:
            # дополняем справа нулями до 8 бит
            self.current <<= (8 - self.nbits)
            self.bytes.append(self.current)
            self.current = 0
            self.nbits = 0

    def get_bytes(self):
        return bytes(self.bytes)

class BitReader:
    """Чтение битов из байтовой строки с ограничением по длине битов"""
    def __init__(self, data: bytes, bit_length: int):
        self.data = data
        self.bit_length = bit_length
        self.pos = 0  # позиция в битах

    def read_bit(self):
        if self.pos >= self.bit_length:
            return None
        byte_index = self.pos // 8
        bit_index = 7 - (self.pos % 8)  # читаем старший бит первым
        b = (self.data[byte_index] >> bit_index) & 1
        self.pos += 1
        return '1' if b else '0'

    def read_bits(self, n):
        bits = []
        for _ in range(n):
            bit = self.read_bit()
            if bit is None:
                return None
            bits.append(bit)
        return ''.join(bits)

# ====================== Компрессия ======================

def compress_to_file(input_file, output_file, window_size=1024):
    # читаем как байты
    with open(input_file, 'rb') as f:
        data = f.read()

    if not data:
        print("Input file is empty.")
        # всё равно создаём пустой файл с заголовком
        with open(output_file, 'wb') as f_out:
            pickle.dump((window_size, 0), f_out)
        return

    window = deque(maxlen=window_size)  # хранит int (0..255)
    freq = Counter()
    writer = BitWriter()

    root = None
    codes = {}

    # Проходим по каждому байту (int)
    for b in data:
        # Кодирование: префикс + либо 8 бит нового байта, либо код Хаффмана
        if root is not None and b in codes:
            # префикс '1' означает: далее код Хаффмана
            writer.write_bits('1')
            writer.write_bits(codes[b])
        else:
            # префикс '0' означает: далее 8 бит "сырых" данных (новый байт)
            writer.write_bits('0')
            writer.write_bits(f'{b:08b}')

        # Обновление окна и частот
        if len(window) == window_size:
            old = window.popleft()
            freq[old] -= 1
            if freq[old] == 0:
                del freq[old]

        window.append(b)
        freq[b] += 1

        # Перестроение дерева и кодов
        if freq:
            root = build_huffman_tree(freq)
            if root:
                codes = generate_codes(root)
        else:
            root = None
            codes = {}

    # Завершаем запись битов
    writer.flush()
    compressed_bytes = writer.get_bytes()
    bit_length = writer.total_bits

    # Сохраняем заголовок и данные
    with open(output_file, 'wb') as f:
        pickle.dump((window_size, bit_length), f)
        f.write(compressed_bytes)

    ratio = len(compressed_bytes) / len(data) if len(data) > 0 else 0
    print(f"Compressed {input_file} → {output_file} (window={window_size}, ratio ≈ {ratio:.3f})")

# ====================== Декомпрессия ======================

def decompress_from_file(input_file, output_file):
    with open(input_file, 'rb') as f:
        window_size, bit_length = pickle.load(f)
        compressed_bytes = f.read()

    reader = BitReader(compressed_bytes, bit_length)

    window = deque(maxlen=window_size)
    freq = Counter()
    decompressed = bytearray()
    root = None

    while True:
        flag = reader.read_bit()
        if flag is None:
            break  # конец потока
        if flag == '0':
            # новый байт: читаем 8 бит
            bits = reader.read_bits(8)
            if bits is None:
                raise ValueError("Unexpected end of bitstream while reading raw byte")
            b = int(bits, 2)
            decompressed.append(b)

            # обновляем окно/частоты
            if len(window) == window_size:
                old = window.popleft()
                freq[old] -= 1
                if freq[old] == 0:
                    del freq[old]
            window.append(b)
            freq[b] += 1

            # перестроение дерева
            root = build_huffman_tree(freq) if freq else None
            continue

        # flag == '1' => код Хаффмана
        if root is None:
            raise ValueError("Huffman tree missing for coded symbol")

        # Если дерево состоит из одного листа, берем его сразу
        if root.char is not None:
            b = root.char
            decompressed.append(b)
            if len(window) == window_size:
                old = window.popleft()
                freq[old] -= 1
                if freq[old] == 0:
                    del freq[old]
            window.append(b)
            freq[b] += 1
            root = build_huffman_tree(freq) if freq else None
            continue

        # Иначе спускаемся по дереву, читая биты
        current = root
        while current.char is None:
            bit = reader.read_bit()
            if bit is None:
                raise ValueError("Unexpected end of bitstream while reading Huffman code")
            current = current.left if bit == '0' else current.right
            if current is None:
                raise ValueError("Invalid Huffman code encountered during decoding")

        b = current.char
        decompressed.append(b)

        # обновляем окно/частоты
        if len(window) == window_size:
            old = window.popleft()
            freq[old] -= 1
            if freq[old] == 0:
                del freq[old]
        window.append(b)
        freq[b] += 1

        # перестроение дерева
        root = build_huffman_tree(freq) if freq else None

    # Записываем восстановленные байты
    with open(output_file, 'wb') as f:
        f.write(decompressed)

    print(f"Decompressed {input_file} → {output_file}")

# ====================== main ======================

def main():
    if len(sys.argv) < 2:
        print("Usage: python huffman_adaptive.py <input_file> [window_size]")
        sys.exit(1)

    input_file = sys.argv[1]
    window_size = int(sys.argv[2]) if len(sys.argv) > 2 else 1024

    compressed_file = "compressed_adaptive.huff"
    decompressed_file = "decompressed.bin"

    compress_to_file(input_file, compressed_file, window_size)
    decompress_from_file(compressed_file, decompressed_file)

    # Проверка: сравниваем байты
    with open(input_file, 'rb') as f_in, open(decompressed_file, 'rb') as f_out:
        original = f_in.read()
        restored = f_out.read()
        if original == restored:
            print("✓ Decompression successful!")
        else:
            print("✗ Decompression failed!")
            # для отладки можно вывести первые несовпадающие позиции
            min_len = min(len(original), len(restored))
            for i in range(min_len):
                if original[i] != restored[i]:
                    print(f"First mismatch at byte {i}: original={original[i]} restored={restored[i]}")
                    break
            if len(original) != len(restored):
                print(f"Lengths differ: original={len(original)} restored={len(restored)}")

if __name__ == "__main__":
    main()
