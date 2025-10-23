"""
File chunking module for data-over-sound transmission.

This module provides functions to encode files into chunks for transmission
and decode received chunks back into files.
"""

from rust_enum import enum, Case
import os
from math import ceil

# Constants for chunk protocol
CHUNK_INDEX_BYTES = 2
NUM_CHUNKS_BYTES = 2
FILE_SIZE_BYTES = 4
CHUNK_HEADER_SIZE = CHUNK_INDEX_BYTES + NUM_CHUNKS_BYTES
FILE_METADATA_HEADER = b'$$$$FILE'
FILE_FOOTER = b'FEND$$$$'
MIN_METADATA_SIZE = len(FILE_METADATA_HEADER) + FILE_SIZE_BYTES


@enum
class Result:
    """Result type for chunking operations."""
    Ok = Case(value=bytearray)
    Err = Case(value=list[int])  # list of indices that failed


def chunk_by_idx(file, chunk_size, chunk_idcs=None):
    """
    Encode specific chunks from a file.
    
    Args:
        file: Path to file to chunk
        chunk_size: Size of each chunk in bytes
        chunk_idcs: Indices of chunks to yield, or None for all chunks
        
    Yields:
        Encoded chunks with headers
    """
    file_size = os.path.getsize(file)
    # Using ceil for integer division that rounds up
    num_chunks = ceil(file_size / chunk_size)
    
    with open(file, 'rb') as f:
        if chunk_idcs is None:
            yield from chunk(file, chunk_size, called_from_chunk_by_idx=True)
            return
        for i in chunk_idcs:
            f.seek(i * chunk_size)
            # Yield chunk with index and total count headers
            yield (i.to_bytes(CHUNK_INDEX_BYTES, 'big') + 
                   num_chunks.to_bytes(NUM_CHUNKS_BYTES, 'big') + 
                   f.read(chunk_size))

def chunk(file, chunk_size, called_from_chunk_by_idx=False):
    """
    Encode all chunks from a file.
    
    Args:
        file: Path to file to chunk
        chunk_size: Size of each chunk in bytes
        called_from_chunk_by_idx: Internal flag to skip metadata
        
    Yields:
        Encoded chunks with headers, plus metadata and footer if not called internally
        
    Raises:
        ValueError: If filename is too long for chunk size
    """
    file_size = os.path.getsize(file)
    num_chunks = ceil(file_size / chunk_size)
    
    # Yield metadata header if not called internally
    if not called_from_chunk_by_idx:
        filename_bytes = file.encode("utf-8")
        metadata = FILE_METADATA_HEADER + file_size.to_bytes(FILE_SIZE_BYTES, 'big') + filename_bytes
        
        # Validate filename length
        if len(metadata) > chunk_size:
            raise ValueError(
                f"Filename too long: {len(filename_bytes)} bytes. "
                f"Maximum is {chunk_size - MIN_METADATA_SIZE} bytes for chunk_size={chunk_size}"
            )
        yield metadata
    
    # Yield file chunks
    with open(file, 'rb') as f:
        for i, chunk_data in enumerate(iter(lambda: f.read(chunk_size), b'')):
            # Note: chunk index limited to 2 bytes (0-65535)
            if i >= 2**16:
                raise ValueError(f"File too large: exceeds maximum of {2**16} chunks")
            yield (i.to_bytes(CHUNK_INDEX_BYTES, 'big') + 
                   num_chunks.to_bytes(NUM_CHUNKS_BYTES, 'big') + 
                   chunk_data)
    
    # Yield footer if not called internally
    if not called_from_chunk_by_idx:
        yield FILE_FOOTER


def dechunk(chunk_list):
    """
    Decode a list of chunks back into file data.
    
    Args:
        chunk_list: List of encoded chunks (bytes)
        
    Returns:
        Result.Ok(bytearray) if successful with complete file data
        Result.Err(list[int]) with list of missing chunk indices if incomplete
        
    Raises:
        ValueError: If chunk_list is empty or malformed
    """
    if not chunk_list:
        raise ValueError("chunk_list cannot be empty")
    
    # Filter out metadata and footer chunks
    chunk_list = [
        chunk for chunk in chunk_list 
        if len(chunk) >= 8 and
           chunk[0:8] != FILE_FOOTER and 
           chunk[0:8] != FILE_METADATA_HEADER
    ]
    
    if not chunk_list:
        raise ValueError("No valid data chunks found")
    
    # Sort chunks by index
    chunk_list.sort(key=lambda x: int.from_bytes(x[0:CHUNK_INDEX_BYTES], 'big'))
    
    # Get total number of chunks from first chunk
    num_chunks = int.from_bytes(chunk_list[0][CHUNK_INDEX_BYTES:CHUNK_HEADER_SIZE], 'big')
    
    # Check for missing chunks
    chunk_idcs = [int.from_bytes(chunk[0:CHUNK_INDEX_BYTES], 'big') for chunk in chunk_list]
    failed = [i for i in range(num_chunks) if i not in chunk_idcs]
    
    if failed:
        return Result.Err(failed)
    
    # Reassemble file data
    file_data = bytearray()
    for chunk in chunk_list:
        # Extract data part (skip index and count headers)
        raw_chunk = chunk[CHUNK_HEADER_SIZE:]
        file_data.extend(raw_chunk)
    
    return Result.Ok(file_data)


#[cfg(test)]  # this is a valid python comment that looks rusty
def test_chunker():
    # test the chunker
    chunk_size = 128
    with open('files/helloworld.txt', 'rb') as f:
        file_data = f.read()
    file = 'files/helloworld.txt'
    chunks = list(chunk(file, chunk_size))
    print(len(chunks))
    match dechunk(chunks):
        case Result.Ok(data):
            assert data == file_data
        case Result.Err(failed):
            assert False, f"Failed chunks: {failed}"
    # lets now break the chunks, miss second and fourth chunk
    chunks.pop(4)
    chunks.pop(2)  # what fool was i, before i popped 2 and 4, and the 4th moved to 3rd place!!!
    match dechunk(chunks):
        case Result.Ok(data):
            assert False, "Should have failed"
        case Result.Err(failed):
            print(failed)
            assert failed == [1, 3]


if __name__ == '__main__':
    test_chunker()
    print("All tests passed")