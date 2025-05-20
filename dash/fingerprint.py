import re

cache_regex = re.compile(r"^v[\w-]+m[0-9a-fA-F]+$")
version_clean = re.compile(r"[^\w-]")


def build_fingerprint(path, version, hash_value):
    path_parts = path.split("/")
    filename, extension = path_parts[-1].split(".", 1)
    file_path = "/".join(path_parts[:-1] + [filename])
    v_str = re.sub(version_clean, "_", str(version))

    return f"{file_path}.v{v_str}m{hash_value}.{extension}"


def check_fingerprint(path):
    # Use rpartition to avoid splitting the whole path
    head, sep, tail = path.rpartition("/")
    name_parts = tail.split(".")

    # Check if the resource has a fingerprint
    if len(name_parts) > 2 and cache_regex.match(name_parts[1]):
        # Form the original name directly
        if len(name_parts) == 3:
            original_name = f"{name_parts[0]}.{name_parts[2]}"
        else:
            # Only join if strictly necessary
            original_name = ".".join([name_parts[0]] + name_parts[2:])
        # Join head and new filename, avoid joining whole list
        if sep:
            # There was a directory separator
            return f"{head}/{original_name}", True
        else:
            # No separator, just return filename
            return original_name, True

    return path, False
