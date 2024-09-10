import ndjson
import collections
import json
from pathlib import Path
import re
import sys
from kibana_ql import KqlParser


class MockAlwaysContains(object):
    def __contains__(self, _):
        return True


def read_dashboard_library(source: Path):
    result = collections.defaultdict(lambda: [])
    with open(source, "r") as sourcefile:
        data = ndjson.load(sourcefile)
    for item in data:
        if "type" not in item:
            continue
        result[item["type"]].append(item)
    return result


def traverse_fields(ast):
    if "left" in ast and "right" in ast:
        return traverse_fields(ast["left"]) + traverse_fields(ast["right"])
    elif "field" in ast:
        return [ast["field"]]
    else:
        print("# Unable to retrieve fields from tree:", ast, file=sys.stderr)
        return []


def fields_from_kuery(kuery):
    p = KqlParser()
    tree = p.parse(kuery)
    ast = p.ast(tree)
    fields = traverse_fields(ast)
    print("# Kuery fields:", repr(kuery), "-->", fields, file=sys.stderr)
    return fields


def field_filter_search(search, fields):
    has_fields = search["attributes"]["columns"]
    has_fields = list(filter(lambda s: s != "_source", has_fields))

    search_source = json.loads(
        search["attributes"]["kibanaSavedObjectMeta"]["searchSourceJSON"]
    )

    if "query" in search_source and search_source["query"]["language"] == "kuery":
        has_fields += fields_from_kuery(search_source["query"]["query"])
    else:
        print(
            "Non-Kuery Search, skipping:",
            search_source.get("query", None),
            file=sys.stderr,
        )

    safety = (
        "~> Fields are safe"
        if all(has_field in fields for has_field in has_fields)
        else "~> Filtered out"
    )
    print("Search fields:", has_fields, safety, file=sys.stderr)
    return all(has_field in fields for has_field in has_fields)


def field_filter_visualization(visualization, fields):
    vis_state = json.loads(visualization["attributes"]["visState"])

    has_fields = []

    aggs = vis_state.get("aggs", [])
    for agg in aggs:
        if "params" in agg and "field" in agg["params"]:
            has_fields.append(agg["params"]["field"])

    params = vis_state.get("params", {})
    if "controls" in params:
        for control in params["controls"]:
            has_fields.append(control["fieldName"])

    safety = (
        "~> Fields are safe"
        if all(has_field in fields for has_field in has_fields)
        else "~> Filtered out"
    )
    print("Vis fields:", has_fields, safety, file=sys.stderr)
    return all(has_field in fields for has_field in has_fields)


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        print(
            "Usage: field_filter [filename]\n\nFilename should be .ndjson",
            file=sys.stderr,
        )
        sys.exit(1)
    elif not sys.argv[1].endswith(".ndjson"):
        print("WARN: Filename should be .ndjson", file=sys.stderr)
    source = sys.argv[1]

    dashlib = read_dashboard_library(source)
    filters = {
        "search": field_filter_search,
        "visualization": field_filter_visualization,
    }

    # TODO make this an arg
    try:
        with open("data/fields.txt", "r") as key_file:
            key_set = set(key_file.read().splitlines())
    except FileNotFoundError:
        key_set = MockAlwaysContains()

    for item_type, items in dashlib.items():
        if item_type in filters:
            dashlib[item_type] = list(
                filter(lambda i: filters[item_type](i, key_set), items)
            )
