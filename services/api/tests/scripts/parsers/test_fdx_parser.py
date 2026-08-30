import pytest
from clearcut.scripts.adapters.fdx_parser import FdxParser
from clearcut.scripts.domain.elements import ElementType


def test_parse_valid_fdx():
    parser = FdxParser()
    fdx_xml = """<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Template="No" Version="1">
  <Content>
    <Paragraph Type="Scene Heading">
      <Text>INT. DETECTIVE OFFICE - NIGHT</Text>
    </Paragraph>
    <Paragraph Type="Action">
      <Text>Detective MILLER pours whiskey into a crystal glass.</Text>
    </Paragraph>
    <Paragraph Type="Character">
      <Text>MILLER</Text>
    </Paragraph>
    <Paragraph Type="Dialogue">
      <Text>It was a cold night in Chicago.</Text>
    </Paragraph>
  </Content>
</FinalDraft>"""
    result = parser.parse(fdx_xml.encode("utf-8"), "detective.fdx")
    assert len(result.elements) == 4
    assert result.elements[0].element_type == ElementType.SCENE_HEADING
    assert result.elements[1].element_type == ElementType.ACTION
    assert result.elements[2].element_type == ElementType.CHARACTER
    assert result.elements[3].element_type == ElementType.DIALOGUE


def test_hostile_xml_entity_expansion_rejected():
    parser = FdxParser()
    billion_laughs = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ELEMENT lolz (#PCDATA)>
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;">
]>
<FinalDraft>
  <Content><Paragraph Type="Action"><Text>&lol1;</Text></Paragraph></Content>
</FinalDraft>"""
    with pytest.raises(ValueError, match="Entity expansion or DTD forbidden"):
        parser.parse(billion_laughs.encode("utf-8"), "malicious.fdx")
