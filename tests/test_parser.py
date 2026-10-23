from app.parser import parse_text,flatten

def test_duplicate_headings_remain_distinct_and_keep_parents():
    tree=parse_text('1 Safety\nIntro.\n1.1 Warning\nFirst warning.\n2 Operation\n2.1 Warning\nSecond warning.')
    assert tree[0].children[0].heading==tree[1].children[0].heading=='Warning'
    assert tree[0].children[0] is not tree[1].children[0]
    assert tree[0].children[0].body=='First warning.'
    assert tree[1].children[0].body=='Second warning.'

def test_skipped_section_numbers_keep_numeric_hierarchy():
    tree=parse_text('1 Overview\nStart.\n1.2.3 Detailed step\nDetail.')
    assert tree[0].level==1
    assert tree[0].children[0].level==3
    assert tree[0].children[0].heading=='Detailed step'

def test_repeated_page_headers_and_page_numbers_are_discarded():
    tree=parse_text('CardioTrack CT-200\n1 Safety\nBody\n2\nCardioTrack CT-200\n1.1 Warning\nDanger')
    assert len(tree)==1
    assert tree[0].body=='Body'
    assert tree[0].children[0].body=='Danger'

def test_list_subitems_are_not_promoted_to_top_level_headings():
    tree=parse_text('1 Operation\nA. Press Start\n- Wait for display.\nB. Read result')
    assert len(tree)==1
    assert [x.heading for x in tree[0].children]==['Press Start','Read result']
