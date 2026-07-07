from __future__ import annotations

import struct

XMP_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"


def packet(video_length: int, timestamp_us: int) -> bytes:
    xml = f'''<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:Camera="http://ns.google.com/photos/1.0/camera/" xmlns:Container="http://ns.google.com/photos/1.0/container/" xmlns:Item="http://ns.google.com/photos/1.0/container/item/" Camera:MotionPhoto="1" Camera:MotionPhotoVersion="1" Camera:MotionPhotoPresentationTimestampUs="{timestamp_us}" Camera:MicroVideo="1" Camera:MicroVideoVersion="1" Camera:MicroVideoOffset="{video_length}" Camera:MicroVideoPresentationTimestampUs="{timestamp_us}">
   <Container:Directory><rdf:Seq>
    <rdf:li rdf:parseType="Resource"><Container:Item Item:Mime="image/jpeg" Item:Semantic="Primary" Item:Length="0" Item:Padding="0"/></rdf:li>
    <rdf:li rdf:parseType="Resource"><Container:Item Item:Mime="video/mp4" Item:Semantic="MotionPhoto" Item:Length="{video_length}"/></rdf:li>
   </rdf:Seq></Container:Directory>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>'''.encode("utf-8")
    payload = XMP_HEADER + xml
    if len(payload) + 2 > 65535:
        raise ValueError("XMP packet is too large for JPEG APP1")
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def inject_xmp(jpeg_path, output_path, video_length: int, timestamp_us: int) -> None:
    with open(jpeg_path, "rb") as source:
        if source.read(2) != b"\xff\xd8":
            raise ValueError("not a JPEG")
        rest = source.read()
    with open(output_path, "wb") as output:
        output.write(b"\xff\xd8")
        output.write(packet(video_length, timestamp_us))
        output.write(rest)
