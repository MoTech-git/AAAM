from __future__ import print_function

from sys import argv
from ctypes import *
from pathlib import Path
import os
import tempfile

def _load_libsp():
    here = Path(__file__).resolve().parent
    candidates = [
        here / "build" / "liblsp.dylib",
        here / "build" / "liblsp.so",
        here / "build" / "liblsp.dll",
        here / "liblsp.dylib",
        here / "liblsp.so",
        here / "liblsp.dll",
    ]
    for path in candidates:
        if path.exists():
            return cdll.LoadLibrary(str(path))
    try:
        return cdll.LoadLibrary("./build/liblsp.so")
    except OSError as exc:
        expected = ", ".join(str(p) for p in candidates)
        message = (
            "liblsp not found. Build the library and ensure it exists in build/. "
            "Expected one of: {0}. Original error: {1}"
        ).format(expected, exc)
        raise OSError(message)

libsp = _load_libsp()
libsp.distance.restype = c_double

class ShortestPath(Structure):
    @property
    def origin(self):
        return libsp.origin(byref(self))

    def distance(self, destination):
        return libsp.distance(byref(self), destination)

    def parent(self, destination):
        return libsp.parent(byref(self), destination)

    def route(self, destination):
        if destination != self.origin:
            parent = self.parent(destination)
            yield from self.route(parent)
            yield parent, destination
    def clear(self):
        return libsp.clear(byref(self))

libsp.dijkstra.restype = POINTER(ShortestPath)

class Graph(Structure):
    def dijkstra(self, origin, destination):
        return libsp.dijkstra(byref(self), origin, destination).contents
    def update_edge(self, origin, destination, weight):
        return libsp.update_edge(byref(self), origin, destination, weight)
    def writegraph(self, filename):
        return libsp.writegraph(byref(self), filename)

libsp.simplegraph.restype = POINTER(Graph)
libsp.readgraph.restype = POINTER(Graph)

def simplegraph(directed=True):
    return libsp.simplegraph(directed).contents


def readgraph(filename, directed=True):
    return libsp.readgraph(filename, directed).contents


def from_dataframe(df, start_col, end_col, weight_col, directed=True):
    cols = [start_col, end_col, weight_col]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError("Missing columns in links_df: {0}".format(", ".join(missing)))

    max_id = int(max(df[start_col].max(), df[end_col].max()))
    edge_count = int(len(df))

    # Write MatrixMarket to a temp file, then load via C++ reader.
    here = Path(__file__).resolve().parent
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".mtx",
            prefix="sp_graph_",
            dir=str(here),
            delete=False,
        ) as tmp:
            temp_file = tmp.name
            tmp.write("%%MatrixMarket matrix coordinate real general\n%\n")
            tmp.write("{0} {0} {1}\n".format(max_id, edge_count))
            for v1, v2, w in df[cols].itertuples(index=False, name=None):
                tmp.write("{0} {1} {2}\n".format(int(v1), int(v2), float(w)))
        return readgraph(temp_file.encode(), directed)
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except OSError:
                pass


def test():
    g = simplegraph()
    #g = readgraph(b"../sf.mtx")
    res = g.update_edge(1, 3, c_double(0.5))
    sp = g.dijkstra(1, -1)

    print("origin:", sp.origin)
    g.writegraph(b"test.mtx")
    for destination in [2, 3]:
        print(destination, sp.distance(destination))

        print( " -> ".join("%s"%vertex[1] for vertex in sp.route(destination)) )

if __name__ == '__main__':
    test()
