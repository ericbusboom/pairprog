"""Tool access for the filesystem"""

from pathlib import Path
from fsspec.implementations.local import LocalFileSystem, AbstractFileSystem
from fsspec.implementations.dirfs import DirFileSystem
import unittest

class FSAccess:

    def __init__(self, fs: Path|str|AbstractFileSystem) -> None:
        """
        Initialize an FSAccess object.

        Args:
            fs (Path|str|AbstractFileSystem): The file system or file system path to use.
        """
        if isinstance(fs, (Path, str)):
            self.fs = DirFileSystem(str(fs),LocalFileSystem())
        else:
            self.fs = fs

    def read(self, path: str, encoding=None) -> str:
        """
        Read text from a file.

        Args:
            path (str): The path to the file to be read.
            encoding (str, optional): The encoding to use for reading the file.

        Returns:
            str: The content of the file as a string.
        """
        with self.fs.open(path, "r", encoding=encoding) as f:
            return f.read()

    def write(self, path: str, b: str, encoding=None) -> None:
        """
        Write text to a file.

        Args:
            path (str): The path to the file to be written.
            b (str): The text content to write to the file.
            encoding (str, optional): The encoding to use for writing the file.
        """
        with self.fs.open(path, "w", encoding=encoding) as f:
            f.write(b)

    def ls(self, path: str) -> list:
        """
        List files in a directory.

        Args:
            path (str): The path to the directory.

        Returns:
            list: A list of file names in the specified directory.
        """
        return self.fs.ls(path)


class TestCase(unittest.TestCase):

    def test_basic(self):
        fs = FSAccess("/Volumes/Cache/cache/scratch")
        fs.write("test2.txt", "Hello world!")
        self.assertEqual(fs.read("test2.txt"), "Hello world!")
        #fs.fs.rm("test.txt")
