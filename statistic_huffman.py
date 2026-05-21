import heapq
from collections import Counter
import pickle
import sys


# -----------------------------
#   Узел дерева Хаффмана
# -----------------------------
class Node:
    def __init__(self, byte=None, freq=0, left=None, right=None):
        self.byte = byte      # значение байта (0–255) или None
        self.freq = freq
        self.left = left
        self.right = right

    def __lt__(self, other):
        return self.freq < other.freq


# -----------------------------
#   Построение дерева
# -----------------------------
def build_huffman_tree(freqs):
    heap = [Node(byte, freq) for byte, freq in freqs.items()]
    heapq.heapify(heap)

    if len(heap) == 1:
        # Специальный случай: файл состоит из одного байта
        only = heapq.heappop(heap)
        return Node(None, only.freq, only, None)

    while len(heap) > 1:
        a = heapq.heappop(heap)
        b = heapq.heappop(heap)
        parent = Node(None, a.freq + b.freq, a, b)
        heapq.heappush(heap, parent)

    return heap[0]


# -----------------------------
#   Генерация кодов
# -----------------------------
def generate_codes(node, prefix="", table=None):
    if table is None:
        table = {}

    if node.byte is not None:
        table[node.byte] = prefix
        return table

    generate_codes(node.left, prefix + "0", table)
    if node.right:
        generate_codes(node.right, prefix + "1", table)

    return table


# -----------------------------
#   Биты → байты
# -----------------------------
def bitstring_to_bytes(bits):
    out = bytearray()
    for i in range(0, len(bits), 8):
        chunk = bits[i:i+8]
        if len(chunk) < 8:
            chunk = chunk.ljust(8, "0")
        out.append(int(chunk, 2))
    return bytes(out)


# -----------------------------
#   Байты → биты
# -----------------------------
def bytes_to_bitstring(data):
    return "".join(f"{byte:08b}" for byte in data)


# -----------------------------
#   Сжатие
# -----------------------------
def compress_to_file(input_file, output_file):
    with open(input_file, "rb") as f:
        data = f.read()

    if not data:
        print("Input file is empty.")
        return

    freqs = Counter(data)
    root = build_huffman_tree(freqs)
    codes = generate_codes(root)

    bitstring = "".join(codes[b] for b in data)
    bit_length = len(bitstring)
    compressed_bytes = bitstring_to_bytes(bitstring)

    with open(output_file, "wb") as f:
        pickle.dump((freqs, bit_length), f)
        f.write(compressed_bytes)

    print(f"Compressed: {input_file} → {output_file}")


# -----------------------------
#   Декомпрессия
# -----------------------------
def decompress_from_file(input_file, output_file):
    with open(input_file, "rb") as f:
        freqs, bit_length = pickle.load(f)
        compressed_bytes = f.read()

    root = build_huffman_tree(freqs)
    bits = bytes_to_bitstring(compressed_bytes)[:bit_length]

    out = bytearray()
    node = root

    for bit in bits:
        node = node.left if bit == "0" else node.right
        if node.byte is not None:
            out.append(node.byte)
            node = root

    with open(output_file, "wb") as f:
        f.write(out)

    print(f"Decompressed: {input_file} → {output_file}")


# -----------------------------
#   main()
# -----------------------------
import time
import os

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else "input.txt"
    compressed = "compressed.huff"
    decompressed = "decompressed.bin"

    # --- Measure input size ---
    input_size = os.path.getsize(input_file)

    # --- Compress ---
    t1 = time.time()
    compress_to_file(input_file, compressed)
    t2 = time.time()

    compressed_size = os.path.getsize(compressed)

    # --- Decompress ---
    t3 = time.time()
    decompress_from_file(compressed, decompressed)
    t4 = time.time()

    # --- Verify correctness ---
    with open(input_file, "rb") as f1, open(decompressed, "rb") as f2:
        ok = (f1.read() == f2.read())

    # --- Print results ---
    print("\n===== HUFFMAN RESULTS =====")
    print(f"Input size:        {input_size} bytes")
    print(f"Compressed size:   {compressed_size} bytes")
    print(f"Compression ratio: {compressed_size / input_size:.3f}")
    print(f"Compress time:     {t2 - t1:.4f} sec")
    print(f"Decompress time:   {t4 - t3:.4f} sec")
    print(f"Correct decode:    {ok}")

if __name__ == "__main__":
    main()
