import time
import sys
import json
import typing
import xxhash
from watchdog.observers import Observer
from watchdog.events import DirModifiedEvent, FileModifiedEvent, FileSystemEventHandler

BUFFER_FILE = "ndedit_data/buffer.json"
MEMORY_FILE = "ndedit_data/_memory.json"


def encodes_json_object(content: str) -> bool:
    content = content.strip()
    if not (content.startswith("{") or content.startswith("[")):
        return False

    try:
        json.loads(content)
        return True
    except json.decoder.JSONDecodeError:
        return False


def memkey(path: list) -> str:
    path = [xxhash.xxh32_hexdigest(path[0]), *path[1:]]
    return ".".join(path)


def simplify_with_memory(record: typing.Any, memory: dict, path=None) -> dict:
    if path is None:
        path = [record["id"] if "id" in record else json.dumps(record)]
    if not isinstance(record, dict):
        return record

    for key, value in record.items():
        next_path = path + [key]
        if isinstance(value, list):
            record[key] = [
                simplify_with_memory(entry, memory, next_path + [str(i)])
                for i, entry in enumerate(value)
            ]
        elif isinstance(value, dict):
            record[key] = simplify_with_memory(value, memory, next_path)
        elif isinstance(value, str) and encodes_json_object(value):
            memory[memkey(next_path)] = "json_str"
            val = json.loads(value)
            if isinstance(val, list):
                record[key] = [simplify_with_memory(entry, memory, next_path + [str(i)]) for i, entry in enumerate(val)]
            else:
                record[key] = simplify_with_memory(val, memory, next_path)
    return record


def create_buffer_content(ndjson_content: list[str]) -> tuple[list, dict]:
    data, memory = [], {}
    for i, line in enumerate(ndjson_content):
        record = json.loads(line)
        record = simplify_with_memory(record, memory)
        data.append(record)

    return data, memory


# Given an NDJson source, create an editable json buffer, and a packaged json buffer
def create_buffers(source: str):
    with open(source, "r") as ndjson_file:
        ndjson_content = ndjson_file.read().splitlines()
    data, memory = create_buffer_content(ndjson_content)
    with open(MEMORY_FILE, "w") as memoryfile:
        json.dump(memory, memoryfile, indent=2)
    with open(BUFFER_FILE, "w") as bufferfile:
        json.dump(data, bufferfile, indent=2)


def flatten_buffer_entry(record: typing.Any, memory: dict, path=None) -> typing.Any:
    if path is None:
        path = [record["id"] if "id" in record else json.dumps(record)]
    if not isinstance(record, dict) and not isinstance(record, list):
        return record

    if isinstance(record, dict):
        for key, value in record.items():
            next_path = path + [key]
            if isinstance(value, list):
                record[key] = [
                    flatten_buffer_entry(entry, memory, next_path + [str(i)])
                    for i, entry in enumerate(value)
                ]
                if memkey(next_path) in memory:
                    record[key] = json.dumps(record[key], separators=(',', ':'))
            elif isinstance(value, dict):
                record[key] = flatten_buffer_entry(value, memory, next_path)
    else:
        record = [flatten_buffer_entry(entry, memory, path + [str(i)]) for i, entry in enumerate(record)]
        
    if memkey(path) in memory:
        return json.dumps(record, separators=(',', ':'))
    return record


# Given a modified buffer, regenerate the ndjson source using the global memory file
def regenerate_source(buffer: str, source: str):
    with open(buffer, "r") as bufferfile:
        data = json.load(bufferfile)
    with open(MEMORY_FILE, "r") as memfile:
        memory = json.load(memfile)

    flattened = [flatten_buffer_entry(entry, memory) for entry in data]
    with open(source, "w") as sourcefile:
        for line in flattened:
            sourcefile.write(json.dumps(line, separators=(',', ':')) + "\n")


class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, buffer, source):
        self._buffer = buffer
        self._source = source
        self._expect_update = None

    def on_modified(
        self, event: typing.Union[DirModifiedEvent, FileModifiedEvent]
    ) -> None:
        src_path = (
            self._buffer if event.src_path.endswith(self._buffer) else self._source
        )
        if self._expect_update == src_path:
            self._expect_update = None
            return
        to_refresh = self._source if src_path == self._buffer else self._buffer

        print("Update:", src_path, "->", to_refresh)
        if src_path == self._source:
            create_buffers(src_path)
            self._expect_update = self._buffer
        else:
            regenerate_source(src_path, self._source)
            self._expect_update = self._source


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: ndedit.py [NDJson file]", file=sys.stderr)
        sys.exit(1)

    source = sys.argv[1]
    with open(source, 'r') as f:
        with open(source + '.bk', 'w') as fbk:
            fbk.write(f.read())
    print("Backed up source to", source + '.bk')

    create_buffers(source)
    print("Created buffer file in ndedit_data")

    event_handler = FileChangeHandler(BUFFER_FILE, source)
    observer = Observer()
    observer.schedule(event_handler, BUFFER_FILE, recursive=True)
    observer.schedule(event_handler, source, recursive=True)
    observer.start()
    print(f"Watching {BUFFER_FILE} and {source}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
