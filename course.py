import heapq  # Для реализации очереди с приоритетом (мин-кучи)
from collections import Counter  # Для подсчета частот символов
import pickle  # Для сериализации метаданных (частот и bit_length)
import sys  # Для аргументов командной строки


# Класс для узла дерева Хаффмана
class Node:
    def __init__(self, char=None, freq=0, left=None, right=None):
        """
        Инициализация узла.
        - char: символ (для листовых узлов), None для внутренних.
        - freq: частота (вес) узла.
        - left, right: левые и правые потомки.
        """
        self.char = char
        self.freq = freq
        self.left = left
        self.right = right

    def __lt__(self, other):
        """
        Перегрузка оператора < для сравнения узлов по частоте (для heapq).
        """
        return self.freq < other.freq


# Функция для подсчета частот
def calculate_frequencies(data):
    """
    Подсчет частоты каждого символа в входных данных.
    - data: строка или последовательность символов.
    Возвращает: словарь Counter с частотами.
    """
    return Counter(data)


# Функция построения дерева Хаффмана
def build_huffman_tree(frequencies):
    """
    Построение дерева Хаффмана на основе частот.
    - frequencies: словарь с частотами символов.
    Возвращает: корень дерева (Node) или None, если данных нет.
    """
    if not frequencies:
        return None
    # Создаем мин-кучу из листовых узлов
    heap = [Node(char, freq) for char, freq in frequencies.items()]
    heapq.heapify(heap)
    # Пока в куче больше одного узла
    while len(heap) > 1:
        # Извлекаем два узла с минимальными частотами
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        # Создаем родительский узел
        parent = Node(None, left.freq + right.freq, left, right)
        # Добавляем обратно в кучу
        heapq.heappush(heap, parent)
    # Оставшийся узел — корень дерева
    return heap[0]


# Функция генерации кодов по дереву
def generate_codes(root, current_code="", codes=None):
    """
    Рекурсивная генерация кодов путем обхода дерева.
    - root: корень дерева.
    - current_code: текущий префикс кода (строка битов).
    - codes: словарь для хранения кодов (символ: код).
    Возвращает: словарь с кодами.
    """
    if codes is None:
        codes = {}
    if root is None:
        return codes
    # Если лист — присваиваем код символу
    if root.char is not None:
        codes[root.char] = current_code
        return codes
    # Рекурсия для левого (0) и правого (1) потомков
    generate_codes(root.left, current_code + "0", codes)
    generate_codes(root.right, current_code + "1", codes)
    return codes


# Функция для преобразования строки битов в байты (с trailing padding)
def bitstring_to_bytes(bitstring):
    """
    Преобразование строки битов ('0101...') в байты с дополнением trailing zeros.
    - bitstring: строка битов.
    Возвращает: bytes объект.
    """
    byte_array = bytearray()
    for i in range(0, len(bitstring), 8):
        byte_str = bitstring[i:i + 8]
        if len(byte_str) < 8:
            byte_str = byte_str.ljust(8, '0')  # Дополняем trailing zeros
        byte_array.append(int(byte_str, 2))
    return bytes(byte_array)


# Функция для преобразования байтов в строку битов
def bytes_to_bitstring(byte_data):
    """
    Преобразование байтов в строку битов.
    - byte_data: bytes объект.
    Возвращает: строку битов.
    """
    return ''.join(f'{byte:08b}' for byte in byte_data)


# Функция сжатия (компрессии) в файл
def compress_to_file(input_file, output_file):
    """
    Сжатие данных из входного файла и запись в выходной бинарный файл.
    - input_file: путь к входному текстовому файлу.
    - output_file: путь к выходному сжатому файлу.
    """
    # Чтение данных
    with open(input_file, 'r', encoding='utf-8') as f:
        data = f.read()

    if not data:
        print("Input file is empty.")
        return

    # Подсчет частот и построение дерева
    frequencies = calculate_frequencies(data)
    root = build_huffman_tree(frequencies)
    codes = generate_codes(root)

    # Сжатие
    compressed_bitstring = ''.join(codes[char] for char in data)
    bit_length = len(compressed_bitstring)  # Сохраняем точную длину бит
    compressed_bytes = bitstring_to_bytes(compressed_bitstring)

    # Запись в файл: pickled (frequencies, bit_length), затем сжатые байты
    with open(output_file, 'wb') as f:
        pickle.dump((frequencies, bit_length), f)
        f.write(compressed_bytes)

    print(f"Compressed {input_file} to {output_file}")


# Функция распаковки (декомпрессии) из файла
def decompress_from_file(input_file, output_file):
    """
    Декомпрессия из сжатого файла и запись в выходной текстовый файл.
    - input_file: путь к сжатому файлу.
    - output_file: путь к выходному декомпрессированному файлу.
    """
    with open(input_file, 'rb') as f:
        # Чтение pickled (frequencies, bit_length)
        frequencies, bit_length = pickle.load(f)
        # Чтение остатка как сжатых байтов
        compressed_bytes = f.read()

    if not frequencies:
        print("No data to decompress.")
        return

    # Восстановление дерева
    root = build_huffman_tree(frequencies)

    # Преобразование байтов в биты и обрезка до оригинальной длины
    compressed_bitstring = bytes_to_bitstring(compressed_bytes)[:bit_length]

    # Декомпрессия
    decompressed = []
    current = root
    for bit in compressed_bitstring:
        if bit == '0':
            current = current.left
        else:
            current = current.right
        if current.char is not None:
            decompressed.append(current.char)
            current = root

    # Запись в файл
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(''.join(decompressed))

    print(f"Decompressed {input_file} to {output_file}")


# Пример использования (функция main)
def main():
    """
    Пример работы алгоритма с файлами.
    Принимает аргумент: python script.py [input_file]
    По умолчанию: input.txt
    """
    input_file = sys.argv[1] if len(sys.argv) > 1 else "input.txt"
    compressed_file = "compressed.huff"
    decompressed_file = "decompressed.txt"

    # Сжатие
    compress_to_file(input_file, compressed_file)

    # Декомпрессия
    decompress_from_file(compressed_file, decompressed_file)

    # Проверка
    with open(input_file, 'r', encoding='utf-8') as f_in, open(decompressed_file, 'r', encoding='utf-8') as f_out:
        if f_in.read() == f_out.read():
            print("Decompression successful!")
        else:
            print("Decompression failed!")


# Запуск примера
if __name__ == "__main__":
    main()
