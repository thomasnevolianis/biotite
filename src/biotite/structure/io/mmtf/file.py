# Copyright 2018 Patrick Kunzmann.
# This source code is part of the Biotite package and is distributed under the
# 3-Clause BSD License. Please see 'LICENSE.rst' for further information.

import numpy as np
import msgpack
import struct
from ....file import File
from ...error import BadStructureError
from .decode import decode_array

__all__ = ["MMTFFile"]


class MMTFFile(File):
    """
    This class represents a MMTF file.
    
    This class provides only a parser for MMTF files.
    Writing MMTF files is not possible at this point.
    """
    
    def __init__(self):
        self._content = None
    
    def read(self, file_name):
        """
        Parse a MMTF file.
        
        Parameters
        ----------
        file_name : str
            The name of the file to be read.
        """
        with open(file_name, "rb") as f:
            self._content = msgpack.unpackb(f.read())
        for key in list(self._content.keys()):
            self._content[key.decode("UTF-8")] = self._content.pop(key)
    
    def write(self, file_name):
        """
        Not implemented yet.        
        """
        raise NotImplementedError()
    
    def get_codec(self, key):
        data = self._content[key]
        if isinstance(data, bytes) and data[0] == 0:
            codec = struct.unpack(">i", data[0:4 ])[0]
            return codec
        else:
            return None
    
    def __getitem__(self, key):
        data = self._content[key]
        if isinstance(data, bytes) and data[0] == 0:
            # MMTF specific format -> requires decoding
            codec     = struct.unpack(">i", data[0:4 ])[0]
            length    = struct.unpack(">i", data[4:8 ])[0]
            param     = struct.unpack(">i", data[8:12])[0]
            raw_bytes = data[12:]
            return decode_array(codec, raw_bytes, param)
        else:
            return data
    
    def __iter__(self):
        return self._content.__iter__()
    
    def __len__(self):
        return len(self._content)