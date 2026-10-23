from app.parser import parse_text,flatten,norm

def test_normalization_matches_compatibility_ligatures():
    assert norm('General Speciﬁcations') == norm('General Specifications')

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


def test_ct200_numbered_clinical_thresholds_stay_in_section_body():
    text = """3 Device Operation
3.3 Result Display and Classification
The device displays a classification indicator.
1. Normal: systolic < 120 and diastolic < 80
2. Elevated: systolic 120-129 and diastolic < 80
3. Hypertension Stage 1: systolic 130-139 or diastolic 80-89
4. Hypertension Stage 2: systolic >= 140 or diastolic >= 90
5. Hypertensive Crisis: systolic > 180 or diastolic > 120"""
    hints = {"3 device operation", "3.3 result display and classification"}
    tree = parse_text(text, heading_hints=hints)
    section = tree[0].children[0]
    assert section.heading == "Result Display and Classification"
    assert "1. Normal:" in section.body
    assert "5. Hypertensive Crisis:" in section.body
    assert len(section.children) == 0


def test_ct200_out_of_order_section_numbers_are_kept_in_reading_order():
    tree = parse_text("3 Device Operation\n3.4 Auto Shutoff\nPowers off after inactivity.\n3.3 Result Display and Classification\nShows the reading.")
    assert [n.heading for n in tree[0].children] == ["Auto Shutoff", "Result Display and Classification"]


def test_ct200_skipped_deep_numeric_heading_level_is_preserved():
    tree = parse_text("2 Physical Specifications\n2.1 General Specifications\n2.1.1.1 Battery Life Under Typical Use\nFour batteries provide 300 cycles.")
    battery = tree[0].children[0].children[0]
    assert battery.level == 4
    assert battery.heading == "Battery Life Under Typical Use"
