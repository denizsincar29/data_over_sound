# this thing is used to encode a file into chunks for a data-over-sound transmitte r
# optionally retrieve specific x-th chunk from a file

from rust_enum import enum, Case
import os  # .path.getsize
from math import ceil

@enum
class Result:
    Ok = Case(value = bytearray)
    Err = Case(value = list[int])  # list of indices that failed

def chunk_by_idx(file, chunk_size, chunk_idcs=None):
    file_size = os.path.getsize(file)
    num_chunks = ceil(file_size / chunk_size)  # stupid python doesn't have // that divides and rounds to the upper integer
    with open(file, 'rb') as f:
        if chunk_idcs is None:  # don't do this, use
            yield from chunk(file, chunk_size, called_from_chunk_by_idx=True)
            return # don't do the following
        for i in chunk_idcs:
            f.seek(i * chunk_size)
            # yield first 2 bytes as chunk index, second 2 bytes as total number of chunks, then the chunk
            yield i.to_bytes(2, 'big') + num_chunks.to_bytes(2, 'big') + f.read(chunk_size)

# lets make an optimized version that yields all chunks without specifying indices
def chunk(file, chunk_size, called_from_chunk_by_idx=False):
    file_size = os.path.getsize(file)
    num_chunks = ceil(file_size / chunk_size)
    # if not called from chunk_by_idx, yield the metadata
    # metadata: b'$$$$FILE' header, 4 bytes for file size, rest of the bytes for the file name
    if not called_from_chunk_by_idx:
        yield b'$$$$FILE' + file_size.to_bytes(4, 'big') + file.encode("utf-8")  # well, if only filename won't be longer than chunksize-12!
    with open(file, 'rb') as f:
        for i, chunk in enumerate(iter(lambda: f.read(chunk_size), b'')): # read until EOF
            yield i.to_bytes(2, 'big') + num_chunks.to_bytes(2, 'big') + chunk  # don't think that a chunk index will ever be >65536, or it will transfer a file for >1 week
    # if not called from chunk_by_idx, yield the FEND$$$$ footer to not make the receiver wait 30 seconds for the next chunk
    if not called_from_chunk_by_idx:
        yield b'FEND$$$$'


def dechunk(chunk_list):
    '''
    dechunks a list of chunks into a file

    args:
        chunk_list: list of chunks, each chunk is a tuple of (chunk_idx, num_chunks, chunk_data)

    returns:
        Result.Ok if successful, Result.Err with a list of indices that failed
    '''
# delete all chunks that start with FEND$$$$ and $$$$FILE
    chunk_list = [chunk for chunk in chunk_list if chunk[0:8] != b'FEND$$$$' and chunk[0:8] != b'$$$$FILE']
    # sort the chunks by index via the first 2 bytes of the chunk
    chunk_list.sort(key=lambda x: int.from_bytes(x[0:2], 'big'))
    num_chunks = int.from_bytes(chunk_list[0][2:4], 'big')
    file = bytearray()
    chunk_idcs = [int.from_bytes(chunk[0:2], 'big') for chunk in chunk_list]
    failed = [i for i in range(num_chunks) if i not in chunk_idcs]
    if failed:
        return Result.Err(failed)
    for i, chunk in enumerate(chunk_list):
        chunk_idx = int.from_bytes(chunk[0:2], 'big')
        # remove the chunk index
        raw_chunk = chunk[4:]
        file.extend(raw_chunk)
    return Result.Ok(file)


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