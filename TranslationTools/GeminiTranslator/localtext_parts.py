"""Split LocalText losslessly into semantic groups; merge only en back by id/key."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Mods/Villain/patch_vh/LocalText.json'
OUTPUT = ROOT / 'TranslationExports/LocalText_PhanLoai'

# First match wins. Names and narrative-specific families precede broad system/UI rules.
RULES = [
    ('01_hoi_thoai', 'Hội thoại và lời nhân vật',
     r'^(?:drama_dialogue|drama_task_dialogue|npc_diagogue|spriteSub_\d|sprite_\d|honorLegendDialogue|xingtian_duihua|schoolTaskLobby_npctalk|pubAsk|pubAnswer|roleAskRelation)'),
    ('02_lua_chon_hoi_thoai', 'Lựa chọn hội thoại', r'^(?:drama_options?|dramaSelectItem|option_fa)'),
    ('03_ky_nang_cong_phap', 'Kỹ năng, công pháp và thuộc tính kỹ năng',
     r'^(?:skill|step|ultimate|ability|passiveMethod|ImmortalMethod|accordMethod|prefix(?:Desc|Name)S|s_\d|SkillGroup|GodEyeSkills|SpecificSkill|honorLegendSkill|honorBearSkill|elderSkill|fieldSkill|GeomancySkil|battleAbility|BattleEffectDesc|inheriteffect|liaojicitiao|chickenskillname|lotusSwordEffect|soleDevourEffect|unlockDesc)'),
    ('04_thien_phu_khi_van', 'Thiên phú, khí vận, đạo tâm và đạo chủng',
     r'^(?:role_feature|fateName|fateDesc|fate\d|TaoistHeart|taoistHeart|TaoistSeed|ImmortalName|ImmortalDesc|nitianRule|qiyun|halo_desc)'),
    ('05_ten_nhan_vat_danh_hieu', 'Tên nhân vật, danh hiệu và chủng tộc',
     r'^(?:npc_name|rolrNameS|elderName|AppellationTitleName|honorLegendName|honorVillageName|honorBearName|SpecificNpcClothingName|fairyChickenName|potmonName|potmonRace|spriteName|sprite_race_|wingmanBaseName|brokenAltar_boosName|battle_unit_name|DLCSelectRole_Unlock|longnv_race|muou_race|zhizhu_race|zhugeChen$|uglyMan$|shuXian$|zhiZhuNv$|muOu$|xueNv$|aoYao$)'),
    ('06_dia_danh_ten_tong_mon', 'Địa danh, tên tông môn và công trình',
     r'^(?:areaName|townName|schoolFirstName|schoolLastName|schoolName(?:First|Second)|school_name_(?:first|second|last)|schoolBuildingName|townBuildingName|building\d|battle_dungeon_name|dungenonSceneName|DLCdungenonSceneName|RuleDungeonName|ancestralHallName|world_building_|weatherName|heresyName_)'),
    ('07_vat_pham', 'Vật phẩm, đan dược, nguyên liệu và vật cưỡi',
     r'^(?:item_|storePropName|makePillName|makePillDesc|liquorName|liquorDesc|group_name|getText|ItemHobbyLevel|itemLevelDesc|props_|prop_)'),
    ('08_trang_thai_hieu_ung', 'Trạng thái và hiệu ứng', r'^(?:effect_|effectClassName|dyn(?:Atk|Speed|Def|Huixing|HPMAX|MPMAX)Desc|astrictAttrAddDesc)'),
    ('09_nhiem_vu', 'Tên, mô tả và hướng dẫn nhiệm vụ',
     r'^(?:task|schoolTaskName|schoolTaskDesc|SchoolTaskAllotTaskName|SchoolTaskAllotTaskDesc|dutyEventName|dutyEventDesc|TownBountyDesc|town_mission|stoneDaomission|ConsultTitle)'),
    ('10_ky_ngo_cot_truyen_thu_tu', 'Kỳ ngộ, cốt truyện và thư từ',
     r'^(?:fortuitous_|casual_event_|fateStoryDesc|letterTitle|letterContent|suit_history|troubleName|troubleDesc|juqing_|drama_kuafu|drama_dungeon|drama_monthLog|yinyangEyeSoul)'),
    ('11_tong_mon', 'Hoạt động và cơ chế tông môn', r'^(?:school|School|dragonDoor|SchoolDepartment|UISchool)'),
    ('12_khi_linh_yeu_thu_linh_vat', 'Khí linh, yêu thú, linh vật và pháp bảo',
     r'^(?:sprite|artifact|Artifact|potmon|wingman|fairyChicken|herd|Herd|devil|Devil|lotus|Lotus|soulDevour|SoulDevour|playerLoseSoulDevour|yinyangEye|piscesPendant|ImmortalStore|shuanghu_|xiusi_|mantun_|yuluan_|liban_|pimeng_|wushe_|zhuolong_)'),
    ('13_nhan_vat_tu_luyen_canh_gioi', 'Nhân vật, chỉ số, tu luyện và cảnh giới',
     r'^(?:role_|player_|playerInfo|npcInfo|npcinfo|npcRelation|AppellationTitle|growWay|grade_|roleAsk|upGrade|fateFeature|nitian_|ganwu_|wuxue_|canwu_|teachSkill|teach_skill|jiyi_|xuexi_|zhaona_|runNPCGoal|nianling|honor_)'),
    ('14_chien_dau_pho_ban', 'Chiến đấu, phó bản và độ khó',
     r'^(?:battle|Battle|dungeon|dungenon|specialBattle|specBattle|conditionDesc|diff|ghostMo|ghostMo|brokenAltar|targetName|targetDesc|winExtraDesc|zhandou|jinrumijing|jinrushihun|mijingxiaohao)'),
    ('15_che_tao_ky_nghe', 'Luyện đan, luyện khí, họa phù và phong thủy',
     r'^(?:refineElixir|lianqi_|lianqi\d|Geomancy|rune|Rune|pillFormula|danfang|elixirtips|build_|getText|town_refine_name|pub_rune|pub_text|genpilong_)'),
    ('16_nhat_ky_thanh_tuu', 'Nhật ký, sự nghiệp và thành tựu',
     r'^(?:MonthLog|monthLog|log|career|achievement|honorLegendDesc|honorLegendSkill|honorLegendDialogue)'),
    ('18_dlc', 'Nội dung và giao diện DLC', r'^(?:D_|d_|dlc|DLC|DLCdungenonSceneName)'),
    ('19_cong_cu_mod', 'Công cụ mod và trình biên tập', r'^(?:mod|Mod|mdo_|s_)'),
    ('20_cap_nhat_khao_sat_tro_giup', 'Lịch sử cập nhật, khảo sát và trợ giúp',
     r'^(?:startGameTip|wenjuan|gamePlan|noticeTitle|noticeContent|Thanks|FAQ|award_title|award_content|game_gengxin|fixData_)'),
    ('17_giao_dien', 'Giao diện, nút bấm, thiết lập và thông báo',
     r'^(?:ui|UI|common_|keyboard_|defaultKeys|handlekey_|setting|shezhi_|gameSetting|login_|game_|map_|minmap_|world_|town_|town[A-Z]|Town|buildingButton|buildingDesc|loading_|loadingText|tip_|tips|intoGame_|notice|gameLevel|gamePlan|level_|option|uiprop|uipotmon|uibattle|uiherd|uifairy|uitown|mobilePaper|upGrade_|ArtBook|artBook|cundang_|jinru|zhuan|betGame|weather|iconStyle|acttips|target|tianyuan|shuxing|shuaxin|suoding|chongsu|tishi|jinggao_|fa$|yifuzhi$|huodejineng$|KuaFuStatusPrompt)'),
]
# Additional legacy spellings and isolated keys reviewed against their Chinese text.
RULES.extend([
    ('01_hoi_thoai', 'Hội thoại và lời nhân vật', r'^(?:dialogRoleChat|xingtian\d|drama_lisilaiye|drama_jibalaile)'),
    ('02_lua_chon_hoi_thoai', 'Lựa chọn hội thoại', r'^(?:chat_|auctionDialogue_(?:qingqiu$|weixie$)|zengsong_(?:jujue|shouxia)$)'),
    ('03_ky_nang_cong_phap', 'Kỹ năng, công pháp và thuộc tính kỹ năng', r'^(?:powerInfo_|rebornSkill_)'),
    ('04_thien_phu_khi_van', 'Thiên phú, khí vận, đạo tâm và đạo chủng', r'^(?:roleFeature|gaiming$)'),
    ('05_ten_nhan_vat_danh_hieu', 'Tên nhân vật, danh hiệu và chủng tộc', r'^(?:danmo$|xuekui$|special\d|immortalAncestralHallName$)'),
    ('06_dia_danh_ten_tong_mon', 'Địa danh, tên tông môn và công trình', r'^(?:village_building_|worldBuildingName$|honorDreamName$)'),
    ('07_vat_pham', 'Vật phẩm, đan dược, nguyên liệu và vật cưỡi', r'^(?:ringName$|ringDesc$|rpointRewardName)'),
    ('08_trang_thai_hieu_ung', 'Trạng thái và hiệu ứng', r'^(?:hftl$|hfll$|hfnl$|tsgj$|tsfy$|cxsj$|zouhuorumo$)'),
    ('09_nhiem_vu', 'Tên, mô tả và hướng dẫn nhiệm vụ', r'^(?:playerTask_|playTask_)'),
    ('10_ky_ngo_cot_truyen_thu_tu', 'Kỳ ngộ, cốt truyện và thư từ', r'^(?:rolrDescS|dieFortuitous$|transfer(?:Name|Desc)$|abortiveAuction(?:Name|Desc)$|mibaoshutips$|dalaoxinmo$|losechance$)'),
    ('11_tong_mon', 'Hoạt động và cơ chế tông môn', r'^(?:callSchool_|standardModelNPC$|attTacticScope|cautiousTacticScope|defendTacticScope|nameFix_|textSchoolDiscount$|textPostDiscount$|dragonschool_|scool_|zongmen)'),
    ('12_khi_linh_yeu_thu_linh_vat', 'Khí linh, yêu thú, linh vật và pháp bảo', r'^(?:resurgeInfo_|qiling_|TalentTip_|fabao_|godEye_|chicken_|immortalEquip_|lifeSkill|LifeSkill_)'),
    ('13_nhan_vat_tu_luyen_canh_gioi', 'Nhân vật, chỉ số, tu luyện và cảnh giới',
     r'^(?:unit_|weapon_|magic_|gradeGrow|grade$|PlayerInfo_|playerinfo_|playerRelation_|playergongji$|playerfangyu$|playertilishangxian$|playerlinglishangxian$|playernianlishangxian$|xiulian_|lundao_|nitianElder_|upgradeElder_|npcDaoxin|noHeroesTupo|daohao_|appellation|taoistSelect_|tupotishi_|relation_|attr_title$|fatefeature_|fate_qiwanghuida$|talent_)'),
    ('14_chien_dau_pho_ban', 'Chiến đấu, phó bản và độ khó', r'^(?:mapBatt(?:le|er)_|matchFight_|ruleDesc|qiecuo_|biwu_|p_meimiaoshanghai$|specialDungeon|difRoleTitle$|difUnitTitle$|difDieTitle$|honorDreamDesc$|AltarStartText$|intoDamgeTestTips$|Skill\d|rule_free$)'),
    ('15_che_tao_ky_nghe', 'Luyện đan, luyện khí, họa phù và phong thủy', r'^(?:liandan_|danlu_|furnaceDurable$|elementNames$|yaoyuanxiaohao$)'),
    ('19_cong_cu_mod', 'Công cụ mod và trình biên tập', r'^compareUnitAreaGrade$'),
    ('20_cap_nhat_khao_sat_tro_giup', 'Lịch sử cập nhật, khảo sát và trợ giúp', r'^(?:jianyi_|planTip$|update_title$|banbenjihua$|conclusionText)'),
    ('17_giao_dien', 'Giao diện, nút bấm, thiết lập và thông báo',
     r'^(?:createPlayer_|getReward_|grid_|itemSelect_|selectItem_|itemType_|store_|transfer_|monthTip_|propSelect_|propInfo_|tempProp_|decorate_|system_|mapmingshan|mapxinshou|yanhuashijian$|guide_|paimaitishi$|movebukeyidong$|load_|itemTitle$|zuoqi_|ditu|shanchucundang$|xinfalantishi$|jianzhu|shijian_|danyaojiemian|bukediuqi$|tesumiaoshu$|duihua$|cundang|paimaiTips|tiaoguo$|wodejipai$|yiyouzongmen$|zhiweirensuyiman$|huifumorenchenggong$|kancetishi$|bawantishi$|chuansong$|leftbutton$|rightbutton$|cost_|wufataopao$|market|mainUI_|maplingqi|mapyaocai|mapkuangcai|eshouhuangyan$|DramaSelectItem$|dramakuafu_|assasinName$|miji_|zuobiao_|tianshubuzu_|email_|martial_|npc_chazhaotishi$|daoru_|dramaDialogue_|auctionDialogue_|jiyudaoju|elderskill_|jiyuyuqi$|ruleProp_|yuehui_|yaoyue_|jiyudayao$|dress_custom$|meiyouchengzhen$|wasActive$|notActive$|dramaFunction_|UnitMonth$|propSell_|book_|banben$|tuichu$|quality$|smooth$|delecttishi$|qiankuohao$|houkuohao$|maohao$|bizhibeijing|kong$|wallPaper_|info_|liaotian_|zengsong|SearchTip$|putMartial$|TaoistSelect_|douhao$|juhao$|dunhao$|immortalHall_|text_|itemGloomEvent|mapBuild$|unHunt_|mapTransmit|energyUiRuins$|skyMonth|yichuzhuxian|fa$|switch_ui_|fairyStoreTip)'),
])
RULES.extend([
    ('05_ten_nhan_vat_danh_hieu', 'Tên nhân vật, danh hiệu và chủng tộc', r'^(?:danmo\d|xuekui\d)'),
    ('06_dia_danh_ten_tong_mon', 'Địa danh, tên tông môn và công trình', r'^(?:worldBuildingName|honorDreamName)'),
    ('07_vat_pham', 'Vật phẩm, đan dược, nguyên liệu và vật cưỡi', r'^(?:ringName|ringDesc)'),
    ('08_trang_thai_hieu_ung', 'Trạng thái và hiệu ứng', r'^zouhuorumo'),
    ('10_ky_ngo_cot_truyen_thu_tu', 'Kỳ ngộ, cốt truyện và thư từ', r'^(?:dieFortuitous|transferName|transferDesc|abortiveAuctionName|abortiveAuctionDesc|mibaoshutips|dalaoxinmo|losechance)'),
    ('13_nhan_vat_tu_luyen_canh_gioi', 'Nhân vật, chỉ số, tu luyện và cảnh giới', r'^grade\d'),
    ('14_chien_dau_pho_ban', 'Chiến đấu, phó bản và độ khó', r'^honorDreamDesc'),
    ('17_giao_dien', 'Giao diện, nút bấm, thiết lập và thông báo', r'^(?:propsInfo_|itemTitle|eshouhuangyan|DramaSelectItem|assasinName|jiyuyuqi|jiyudayao|dress_custom|meiyouchengzhen|mapBuild|energyUiRuins|fa\d)'),
])
COMPILED = [(slug, label, re.compile(pattern)) for slug, label, pattern in RULES]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


def classify(key):
    for slug, label, pattern in COMPILED:
        if pattern.search(key):
            return slug, label
    return '99_can_ra_soat', 'Chưa đủ căn cứ phân loại; cần rà soát'


def split(source, output):
    raw = source.read_bytes()
    rows = json.loads(raw.decode('utf-8-sig'))
    assert isinstance(rows, list)
    assert len({r['key'] for r in rows}) == len(rows), 'Duplicate key'
    assert len({r['id'] for r in rows}) == len(rows), 'Duplicate id'
    if output.exists():
        raise ValueError('Output already exists; choose a new --output folder to preserve edits')
    grouped, labels, entries = defaultdict(list), {}, []
    for ordinal, row in enumerate(rows):
        slug, label = classify(row['key'])
        filename = slug + '.json'
        grouped[filename].append(row)
        labels[filename] = label
        entries.append({'ordinal': ordinal, 'id': row['id'], 'key': row['key'], 'file': filename,
                        'ch_sha256': sha(row['ch'].encode('utf-8'))})
    output.mkdir(parents=True, exist_ok=False)
    for filename, part in sorted(grouped.items()):
        write_new(output / filename, part)
    manifest = {
        'version': 1, 'created': datetime.now(timezone.utc).isoformat(),
        'source': str(source.resolve()), 'source_sha256': sha(raw), 'rows': len(rows),
        'groups': [{'file': name, 'label': labels[name], 'count': len(part)} for name, part in sorted(grouped.items())],
        'entries': entries,
        'rules': [{'group': slug, 'label': label, 'regex': pattern} for slug, label, pattern in RULES],
    }
    write_new(output / '_manifest.json', manifest)
    # Verify the written parts reproduce every original record, in its original order.
    parts = {name: {r['key']: r for r in read(output / name)} for name in grouped}
    rebuilt = [parts[e['file']][e['key']] for e in entries]
    assert rebuilt == rows
    assert source.read_bytes() == raw, 'Original changed during export'
    summary = ['# LocalText — phân loại nội dung', '',
               f'Tổng cộng **{len(rows):,} mục**, chia thành **{len(grouped)} nhóm**.', '',
               'Mỗi mục giữ nguyên toàn bộ id/key/ch/en và thứ tự tương đối trong nhóm. File game gốc không đổi.', '',
               '| File | Nhóm | Số mục |', '|---|---|---:|']
    for name, part in sorted(grouped.items()):
        summary.append(f'| [{name}]({name}) | {labels[name]} | {len(part):,} |')
    summary += ['', 'Phân loại dựa trên nhóm key và kiểm tra mẫu nội dung, không phải phân tích ngữ nghĩa từng câu bằng AI.',
                'Tên và mô tả kỹ năng cùng ở nhóm kỹ năng; tên và mô tả vật phẩm cùng ở nhóm vật phẩm. Nhóm tên riêng tập trung vào nhân vật, danh hiệu và chủng tộc; địa danh có nhóm riêng.',
                'Các câu kể chuyện nằm trong drama_dialogue được giữ cùng mạch hội thoại. Nội dung có ngữ cảnh đặc thù như khí linh, tông môn hoặc DLC được giữ riêng khi không thuộc một nhóm chuyên biệt ở trên.',
                '99_can_ra_soat chứa key chưa khớp quy tắc; không tự đoán và không bỏ sót các mục này.', '',
                'Chỉ nên sửa en. Giữ nguyên id/key/ch. _manifest.json lưu thứ tự và hash nguồn để ghép lại an toàn.',
                'Đây là bộ dữ liệu làm việc ngoài thư mục game; không chép toàn bộ các phần rời vào patch_vh.', '',
                'Ghép kết quả sau khi biên tập (chỉ tạo file xuất, không ghi đè game):', '', '```powershell',
                'python TranslationTools/GeminiTranslator/localtext_parts.py merge', '```',
                'Mặc định tạo LocalText.merged.json bên cạnh thư mục phân loại. Trình ghép chỉ lấy en, đối chiếu id/key/ch và toàn bộ các trường khác, giữ thứ tự gốc. Không tự áp vào game.']
    (output / 'README.md').write_text('\n'.join(summary) + '\n', encoding='utf-8')
    unknown = grouped.get('99_can_ra_soat.json', [])
    counts = Counter(re.sub(r'\d.*$', '', r['key']) for r in unknown)
    write_new(output / '_can_ra_soat_tien_to.json', counts.most_common())
    for name, part in sorted(grouped.items()):
        print(f'{len(part):6}  {name}')
    print('TOTAL', len(rows), 'Original unchanged. Reassembly verified.')


def merge(source, folder, destination):
    manifest = read(folder / '_manifest.json')
    original_raw = source.read_bytes()
    if sha(original_raw) != manifest['source_sha256']:
        raise ValueError('Source changed since split; rebase/re-export before merging')
    original = json.loads(original_raw.decode('utf-8-sig'))
    by_key = {}
    expected_keys = {e['key']: e for e in manifest['entries']}
    for group in manifest['groups']:
        relative = Path(group['file'])
        if relative.name != str(relative) or relative.suffix != '.json':
            raise ValueError('Invalid manifest part path')
        part = read(folder / relative)
        if len(part) != group['count']:
            raise ValueError('Part row count changed: ' + str(relative))
        for row in part:
            key = row['key']
            if key in by_key or key not in expected_keys:
                raise ValueError('Duplicate/unknown key: ' + key)
            entry = expected_keys[key]
            if entry['file'] != str(relative) or entry['id'] != row['id']:
                raise ValueError('Part/id mismatch: ' + key)
            if sha(row['ch'].encode('utf-8')) != entry['ch_sha256']:
                raise ValueError('Chinese source edited: ' + key)
            if not isinstance(row.get('en'), str):
                raise ValueError('en must be a string: ' + key)
            by_key[key] = row
    if set(by_key) != set(expected_keys) or len(original) != manifest['rows']:
        raise ValueError('Missing rows')
    result = []
    for index, row in enumerate(original):
        entry = manifest['entries'][index]
        if entry['ordinal'] != index or entry['key'] != row['key'] or entry['id'] != row['id']:
            raise ValueError('Original order/identity mismatch')
        translated = by_key[row['key']]
        if {k: v for k, v in row.items() if k != 'en'} != {k: v for k, v in translated.items() if k != 'en'}:
            raise ValueError('Non-en field modified: ' + row['key'])
        result.append({**row, 'en': translated['en']})
    if destination.resolve() == source.resolve():
        raise ValueError('Merge is export-only; choose a destination outside the source file')
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_new(destination, result)
    print('Merged', len(result), 'rows ->', destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['split', 'merge'])
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--merged', type=Path, default=OUTPUT.parent / 'LocalText.merged.json')
    args = parser.parse_args()
    if args.command == 'split':
        split(args.source, args.output)
    else:
        merge(args.source, args.output, args.merged)
