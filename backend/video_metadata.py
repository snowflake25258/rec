"""Read standard MP4 movie metadata without an external codec dependency."""
from __future__ import annotations
from pathlib import Path
import struct
from typing import BinaryIO, Iterator


def boxes(stream: BinaryIO,start: int,end: int) -> Iterator[tuple[bytes,int,int]]:
    position=start
    while position+8<=end:
        stream.seek(position)
        size,kind=struct.unpack('>I4s',stream.read(8))
        header=8
        if size==1:
            size=struct.unpack('>Q',stream.read(8))[0];header=16
        elif size==0:size=end-position
        if size<header or position+size>end:raise ValueError('Invalid MP4 box length')
        yield kind,position+header,position+size
        position+=size


def video_metadata(path: Path) -> dict[str,float | int]:
    duration=0.;width=height=0
    with path.open('rb') as stream:
        for kind,start,end in boxes(stream,0,path.stat().st_size):
            if kind!=b'moov':continue
            for child,payload,finish in boxes(stream,start,end):
                if child==b'mvhd':
                    stream.seek(payload);data=stream.read(min(40,finish-payload))
                    if data[0]==0:scale,length=struct.unpack('>II',data[12:20])
                    elif data[0]==1:scale=struct.unpack('>I',data[20:24])[0];length=struct.unpack('>Q',data[24:32])[0]
                    else:raise ValueError('Unknown MP4 movie-header version')
                    if scale:duration=length/scale
                elif child==b'trak':
                    for node,p,e in boxes(stream,payload,finish):
                        if node==b'tkhd':
                            stream.seek(e-8);w,h=struct.unpack('>II',stream.read(8))
                            if w and h:width=max(width,w//65536);height=max(height,h//65536)
    if duration<=0 or not width or not height:raise ValueError('Missing MP4 movie duration or video track')
    return {'duration_seconds':duration,'width':width,'height':height}
