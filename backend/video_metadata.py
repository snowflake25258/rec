"""Read standard MP4 movie metadata without an external codec dependency."""
from __future__ import annotations
from pathlib import Path
import struct
from typing import BinaryIO, Iterator


def boxes(stream: BinaryIO,start: int,end: int) -> Iterator[tuple[bytes,int,int]]:
    # MP4 使用大端 box 结构：普通头 8 字节，size=1 为 64 位扩展长度。
    # size=0 表示延伸到父容器末尾，越界或短于头部的长度立即拒绝。
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
    # 在 moov/mvhd 中读取时间尺度和时长，兼容版本 0/1 的 32/64 位字段。
    # trak/tkhd 最后 8 字节为 16.16 定点宽高；音频轨宽高为零，不参与尺寸选择。
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
