class BlockStorage:
    def __init__(self, num_blocks, block_size):
        self.block_size = block_size
        self.num_blocks = num_blocks
        self.blocks = [bytearray(block_size) for _ in range(num_blocks)]
        self.bitmap = [0] * num_blocks

    def allocate_block(self):
        for i in range(self.num_blocks):
            if self.bitmap[i] == 0:
                self.bitmap[i] = 1
                return i
        return print("Немає доступних блоків")

    def free_block(self, block_index):
        if self.bitmap[block_index] == 1:
            self.bitmap[block_index] = 0
            self.blocks[block_index] = bytearray(self.block_size)

    def write_block(self, block_index, data):
        if len(data) > self.block_size:
            return print("Розмір даних перевищує розмір блоку")
        self.blocks[block_index][:len(data)] = data

    def read_block(self, block_index):
        return self.blocks[block_index]


class FileDescriptor:
    def __init__(self, file_type, max_direct_blocks=10):
        self.file_type = file_type
        self.hard_links = 1
        self.size = 0
        self.direct_blocks = [-1] * max_direct_blocks
        self.indirect_block = -1
        self.symbolic_link = None

    def add_block(self, block_index):
        for i in range(len(self.direct_blocks)):
            if self.direct_blocks[i] == -1:
                self.direct_blocks[i] = block_index
                return
        return print("Немає вільних прямих блоків, потрібен непрямий блок")

    def get_blocks(self):
        return [block for block in self.direct_blocks if block != -1]


class FileSystem:
    def __init__(self, num_blocks, block_size, max_files):
        self.block_storage = BlockStorage(num_blocks, block_size)
        self.max_files = max_files
        self.file_descriptors = [None] * max_files
        self.directory = {}
        self.open_files = {}
        self.next_fd = 0
        self.current_directory = "/"
        self.create_root_directory()

    def create_root_directory(self):
        fd = FileDescriptor('directory')
        self.file_descriptors[0] = fd
        self.directory["/"] = 0

    def mkfs(self, num_descriptors):
        self.__init__(self.block_storage.num_blocks, self.block_storage.block_size, num_descriptors)

    def stat(self, pathname):
        pathname = self.resolve_path(pathname)
        if pathname not in self.directory:
            return print("Файл не знайдено")
        fd_index = self.directory[pathname]
        fd = self.file_descriptors[fd_index]
        return fd

    def ls(self):
        return self.directory

    def create(self, pathname):
        pathname = self.resolve_path(pathname)
        if pathname in self.directory:
            return print("Файл уже існує")
        for i in range(self.max_files):
            if self.file_descriptors[i] is None:
                fd = FileDescriptor('regular')
                self.file_descriptors[i] = fd
                self.directory[pathname] = i
                return
        return print("Досягнуто максимальну кількість файлів")

    def open(self, pathname):
        pathname = self.resolve_path(pathname)
        if pathname not in self.directory:
            return print("Файл не знайдено")
        fd_index = self.directory[pathname]
        fd = self.file_descriptors[fd_index]
        if fd.file_type == 'symlink':
            target = fd.symbolic_link
            return self.open(target)
        self.open_files[self.next_fd] = (fd_index, 0)
        self.next_fd += 1
        return self.next_fd - 1

    def close(self, fd):
        if fd in self.open_files:
            del self.open_files[fd]

    def seek(self, fd, offset):
        if fd in self.open_files:
            fd_index, _ = self.open_files[fd]
            self.open_files[fd] = (fd_index, offset)
        else:
            return print("Файловий дескриптор не знайдено")

    def read(self, fd, size):
        if fd not in self.open_files:
            return print("Файловий дескриптор не знайдено")
        fd_index, offset = self.open_files[fd]
        file_data = bytearray()
        blocks = self.file_descriptors[fd_index].get_blocks()
        total_size = self.file_descriptors[fd_index].size
        if offset + size > total_size:
            size = total_size - offset
        current_offset = offset
        while size > 0:
            block_index = current_offset // self.block_storage.block_size
            block_offset = current_offset % self.block_storage.block_size
            bytes_to_read = min(size, self.block_storage.block_size - block_offset)
            block_data = self.block_storage.read_block(blocks[block_index])
            file_data.extend(block_data[block_offset:block_offset + bytes_to_read])
            size -= bytes_to_read
            current_offset += bytes_to_read
        self.open_files[fd] = (fd_index, current_offset)
        return file_data.decode()

    def write(self, fd, data):
        if fd not in self.open_files:
            return print("Файловий дескриптор не знайдено")
        fd_index, offset = self.open_files[fd]
        fd_obj = self.file_descriptors[fd_index]
        current_offset = offset
        data = data.encode()  # Перетворення даних у байти
        while data:
            block_index = current_offset // self.block_storage.block_size
            block_offset = current_offset % self.block_storage.block_size
            if block_index >= len(fd_obj.direct_blocks) or fd_obj.direct_blocks[block_index] == -1:
                new_block = self.block_storage.allocate_block()
                fd_obj.add_block(new_block)
            block_data = data[:self.block_storage.block_size - block_offset]
            self.block_storage.write_block(fd_obj.direct_blocks[block_index], block_data)
            data = data[len(block_data):]
            current_offset += len(block_data)
        fd_obj.size = max(fd_obj.size, current_offset)
        self.open_files[fd] = (fd_index, current_offset)

    def link(self, name1, name2):
        name1 = self.resolve_path(name1)
        name2 = self.resolve_path(name2)
        if name1 not in self.directory:
            return print("Файл-джерело не знайдено")
        if name2 in self.directory:
            return print("Файл призначення вже існує")
        fd_index = self.directory[name1]
        self.file_descriptors[fd_index].hard_links += 1
        self.directory[name2] = fd_index

    def unlink(self, pathname):
        pathname = self.resolve_path(pathname)
        if pathname not in self.directory:
            return print("Файл не знайдено")
        fd_index = self.directory.pop(pathname)
        fd_obj = self.file_descriptors[fd_index]
        fd_obj.hard_links -= 1
        if fd_obj.hard_links == 0 and fd_index not in [desc[0] for desc in self.open_files.values()]:
            for block in fd_obj.get_blocks():
                self.block_storage.free_block(block)
            self.file_descriptors[fd_index] = None

    def truncate(self, pathname, size):
        pathname = self.resolve_path(pathname)
        if pathname not in self.directory:
            return print("Файл не знайдено")
        fd_index = self.directory[pathname]
        fd_obj = self.file_descriptors[fd_index]
        if size > fd_obj.size:
            current_blocks = len(fd_obj.get_blocks())
            blocks_needed = (size + self.block_storage.block_size - 1) // self.block_storage.block_size
            for _ in range(blocks_needed - current_blocks):
                new_block = self.block_storage.allocate_block()
                fd_obj.add_block(new_block)
            fd_obj.size = size
        elif size < fd_obj.size:
            blocks_to_keep = (size + self.block_storage.block_size - 1) // self.block_storage.block_size
            blocks_to_free = fd_obj.get_blocks()[blocks_to_keep:]
            for block in blocks_to_free:
                self.block_storage.free_block(block)
            fd_obj.direct_blocks = fd_obj.direct_blocks[:blocks_to_keep]
            fd_obj.size = size

    def resolve_path(self, path):
        if not path.startswith("/"):
            path = self.current_directory + "/" + path
        parts = path.split("/")
        resolved_parts = []
        for part in parts:
            if part == "..":
                if resolved_parts:
                    resolved_parts.pop()
            elif part != "." and part:
                resolved_parts.append(part)
        return "/" + "/".join(resolved_parts)

    def mkdir(self, pathname):
        pathname = self.resolve_path(pathname)
        if pathname in self.directory:
            return print("Директорія вже існує")
        for i in range(self.max_files):
            if self.file_descriptors[i] is None:
                fd = FileDescriptor('directory')
                self.file_descriptors[i] = fd
                self.directory[pathname] = i
                return
        return print("Досягнуто максимальну кількість файлів")

    def rmdir(self, pathname):
        pathname = self.resolve_path(pathname)
        if pathname not in self.directory:
            return print("Директорія не знайдена")
        fd_index = self.directory[pathname]
        fd_obj = self.file_descriptors[fd_index]
        if fd_obj.file_type != 'directory':
            return print("Це не директорія")
        if any(name.startswith(pathname + '/') for name in self.directory):
            return print("Директорія не порожня")
        del self.directory[pathname]
        self.file_descriptors[fd_index] = None

    def cd(self, pathname):
        pathname = self.resolve_path(pathname)
        if pathname not in self.directory or self.file_descriptors[self.directory[pathname]].file_type != 'directory':
            return print("Директорія не знайдена")
        self.current_directory = pathname

    def symlink(self, target, linkname):
        linkname = self.resolve_path(linkname)
        if linkname in self.directory:
            return print("Символічне посилання вже існує")
        for i in range(self.max_files):
            if self.file_descriptors[i] is None:
                fd = FileDescriptor('symlink')
                fd.symbolic_link = target
                self.file_descriptors[i] = fd
                self.directory[linkname] = i
                return
        return print("Максимальна кількість досягнутих файлів")


# Створення файлової системи з 100 блоками, кожен розміром 512 байт, і підтримкою до 50 файлів
fs = FileSystem(num_blocks=100, block_size=512, max_files=50)
# Створення нового файлу
fs.create("/myfile.txt")

# Відкриття файлу для запису
fd = fs.open("/myfile.txt")
# Запис даних у файл
data = "My name is Marian"
fs.write(fd, data)

# Закриття файлу після запису
fs.close(fd)
# Відкриття файлу для читання
fd = fs.open("/myfile.txt")

# Читання даних з файлу
read_data = fs.read(fd, len(data))
print("Прочитані дані:", read_data)

# Закриття файлу після читання
fs.close(fd)
# Створення нової директорії
fs.mkdir("/mydir")

# Перехід в нову директорію
fs.cd("/mydir")
print("Поточна директорія:", fs.current_directory)

# Повернення до кореневої директорії
fs.cd("/")
print("Поточна директорія:", fs.current_directory)

# Створення символічного посилання
fs.symlink("/myfile.txt", "/mylink")

# Відкриття символічного посилання для читання
fd_link = fs.open("/mylink")

# Читання даних через символічне посилання
read_data_link = fs.read(fd_link, len(data))
print("Прочитані дані через символічне посилання:", read_data_link)

# Закриття файлу після читання
fs.close(fd_link)
# Видалення символічного посилання
fs.unlink("/mylink")

# Видалення файлу
fs.unlink("/myfile.txt")

# Спроба відкриття видаленого файлу викличе помилку
fs.open("/myfile.txt")

# Вміст кореневої директорії
print("Вміст кореневої директорії:", fs.ls())

# Створення файлу в новій директорії
fs.create("/mydir/newfile.txt")

# Перегляд вмісту директорії після створення нового файлу
print("Вміст директорії '/mydir':", fs.ls())

# Видалення файлу в директорії
fs.unlink("/mydir/newfile.txt")

# Перегляд вмісту директорії після створення нового файлу
print("Вміст директорії '/mydir':", fs.ls())

# Видалення порожньої директорії
fs.rmdir("/mydir")

# Перегляд вмісту директорії після створення нового файлу
print("Вміст директорії '/mydir':", fs.ls())

# Спроба видалити неіснуючу директорію викличе помилку
fs.rmdir("/mydir")
