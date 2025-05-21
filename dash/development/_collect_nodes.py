def is_node(value):
    return value in _NODE_NAMES


def is_shape(value):
    return value in _SHAPE_NAMES


def collect_array(a_value, base, nodes):
    a_type = a_value["name"]
    if a_type in _NODE_NAMES:  # inlined is_node
        nodes.append(base)
    elif a_type in _SHAPE_NAMES:  # inlined is_shape
        collect_nodes(a_value["value"], base + "[]", nodes)
    elif a_type == "union":
        collect_union(a_value["value"], base + "[]", nodes)
    elif a_type == "objectOf":
        collect_object(a_value["value"], base + "[]", nodes)
    return nodes


def collect_union(type_list, base, nodes):
    # Avoid .get because we know the structure of t; indexing is faster than .get for present keys
    for t in type_list:
        t_name = t["name"]
        if t_name in _NODE_NAMES:
            nodes.append(base)
        elif t_name in _SHAPE_NAMES:
            collect_nodes(t["value"], base, nodes)
        elif t_name == "arrayOf":
            collect_array(t["value"], base, nodes)
        elif t_name == "objectOf":
            collect_object(t["value"], base, nodes)
    return nodes


def collect_object(o_value, base, nodes):
    o_name = o_value.get("name")
    o_key = base + "{}"
    if o_name in _NODE_NAMES:
        nodes.append(o_key)
    elif o_name in _SHAPE_NAMES:
        # get("value", {}) is only necessary when the structure might be missing "value"
        collect_nodes(o_value.get("value", {}), o_key, nodes)
    elif o_name == "union":
        collect_union(o_value.get("value"), o_key, nodes)
    elif o_name == "arrayOf":
        collect_array(o_value, o_key, nodes)
    return nodes


def collect_nodes(metadata, base="", nodes=None):
    if nodes is None:
        nodes = []

    for prop_name, value in metadata.items():
        # The "type" key being missing happens for recursive shapes, so must preserve
        t_value = value.get("type", value)
        p_type = t_value.get("name")

        if base:
            key = f"{base}.{prop_name}"
        else:
            key = prop_name

        if p_type in _NODE_NAMES:  # inlined is_node for main paths
            nodes.append(key)
        elif p_type == "arrayOf":
            # t_value should always have "value" (following from profiling)
            collect_array(t_value.get("value", t_value), key, nodes)
        elif p_type in _SHAPE_NAMES:  # inlined is_shape
            collect_nodes(t_value["value"], key, nodes)
        elif p_type == "union":
            collect_union(t_value["value"], key, nodes)
        elif p_type == "objectOf":
            collect_object(t_value.get("value", {}), key, nodes)

    return nodes


def filter_base_nodes(nodes):
    return [n for n in nodes if not any(e in n for e in ("[]", ".", "{}"))]


_NODE_NAMES = {"node", "element"}

_SHAPE_NAMES = {"shape", "exact"}
