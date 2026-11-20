"""Regression checks for map layouts and source-backed balance edits."""
import struct
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from stage_wiki_edits import line_edits, object_edits, wts_edits
from wiki.atlas import ability_command, script_index
from wiki.reachability import callable_functions, creation_contexts, trace
from wiki.map_values import decode_objects, object_table, string_table


def packed_object(parent, uid, fields, extended=False):
    def integer(n):
        return struct.pack("<i", n)
    record = parent + uid + integer(1) + integer(0) + integer(len(fields))
    for field, kind, level, pointer, value in fields:
        record += field + integer(kind)
        if extended:
            record += integer(level) + integer(pointer)
        record += value + parent
    return integer(3) + (integer(1)+record+integer(0) if uid == bytes(4) else integer(0)+integer(1)+record)


class BalanceWiki(unittest.TestCase):
    def test_command_keys_and_positions_follow_separate_cast_and_learn_overrides(self):
        objects={("abilities","A001"):{"parent":"A000","fields":[
            ("ahky",0,0,"X","war3mapSkin.w3a"),("abpx",0,0,1,"war3mapSkin.w3a"),
            ("arhk",0,0,"W","war3map.w3a")]}}
        stock={("abilities","A000"):{"base/units/abilityfunc.txt":{
            "Buttonpos":"0,2","Researchbuttonpos":"1,0","Hotkey":"G","Researchhotkey":"L"}}}
        command=ability_command("A001",objects,stock,False)
        self.assertEqual(command,{"cast":{"key":"X","x":1,"y":2},"learn":{"key":"W","x":1,"y":0}})

    def test_false_registered_condition_and_explicit_execution(self):
        source = """function Reject takes nothing returns boolean
if ( not ( false == true ) ) then
return false
endif
return true
endfunction
function Spawn takes nothing returns nothing
endfunction
function main takes nothing returns nothing
set gg_trg_unused=CreateTrigger()
call TriggerAddCondition(gg_trg_unused, Condition(function Reject))
call TriggerAddAction(gg_trg_unused, function Spawn)
endfunction"""
        self.assertNotIn("Spawn",callable_functions(script_index(source)[0]))
        forced = source.removesuffix("endfunction")+"call TriggerExecute(gg_trg_unused)\nendfunction"
        self.assertIn("Spawn",callable_functions(script_index(forced)[0]))

    def test_siblings_reusing_summon_array_keep_their_own_units_and_spells(self):
        source = """function Summon takes nothing returns nothing
set spell=GetSpellAbilityId()
if spell == 'A001' then
set pool[1]='h001'
call CreateNUnitsAtLoc(1, pool[level], player, where, 0.)
endif
if spell == 'A002' then
set pool[1]='h002'
call CreateNUnitsAtLoc(1, pool[level], player, where, 0.)
endif
endfunction"""
        funcs = script_index(source)[0]
        cases = list(creation_contexts(funcs["Summon"],funcs,{"A001","A002"}).values())
        self.assertEqual([(spells, pools["pool"]) for spells,pools in cases],
                         [({"A001"},{"h001":{1}}),({"A002"},{"h002":{1}})])

    def test_gameplay_trace_follows_nested_summons_without_promoting_parents(self):
        def obj(uid, parent, links=()):
            return {"id":uid,"parent":parent,"stats":[],"linked_fields":[
                {"field":f,"label":f,"level":1,"ids":[i],"source":"fixture"} for f,i in links]}
        objects = {
            "units/H001":obj("H001","H002",[("uhab","A001"),("ureq","hbar")]),
            "units/H002":obj("H002","Ewar"), "units/hbar":obj("hbar","hbar",[("utra","h002")]),
            "units/h002":obj("h002","h002"), "units/h001":obj("h001","h001",[("uabi","A002")]),
            "abilities/A001":obj("A001","A001",[("Hwe1","h001")]),
            "abilities/A002":obj("A002","A002",[("abuf","B001"),("Hwe1","h001")]),
            "effects/B001":obj("B001","B001")}
        metadata={"units":{"uhab":{"type":"heroAbilityList"},"uabi":{"type":"abilityList"},
                           "utra":{"type":"unitList"},"ureq":{"type":"techList"}},
                  "abilities":{"Hwe1":{"type":"unitCode"},"abuf":{"type":"buffList"}}}
        result=trace({"objects":objects,"metadata":metadata,"functions":{},"globals":[],"settings":{},
                      "creation_paths":{},"recipes":[],"models":{},"tables":[],
                      "placements":[{"entry":"war3mapUnits.doo","id":"H001"}]})
        self.assertEqual(result["via"]["effects/B001"],"abilities/A002")
        self.assertEqual(result["via"]["abilities/A002"],"units/h001")
        self.assertEqual(result["via"]["units/h001"],"abilities/A001")
        self.assertEqual(result["parents"],["units/H002"])
        self.assertIn("units/hbar",result["support"])
        self.assertNotIn("units/h002",result["via"])

    def test_level_and_pointer_edit_is_local(self):
        data = packed_object(b"AHwe", b"A001", [(b"Hwe2",0,2,i,struct.pack("<i",v))
                                                for i,v in [(0,2),(1,5)]], True)
        original = []
        list(decode_objects(data, "war3map.w3a", True, {}, lambda *f: original.append(f)))
        uid, field, level, pointer, value, entry, kind, offset, _ = original[-1]
        edit = dict(id=uid, field=field, level=level, pointer=pointer, original=value, kind=kind, offset=offset, value=8)
        result = object_edits(data, entry, [edit])
        self.assertEqual(result, data[:offset]+struct.pack("<i",8)+data[offset+4:])
        with self.assertRaises(ValueError):
            object_edits(result, entry, [edit])
        with self.assertRaises(ValueError):
            object_edits(data, entry, [dict(edit, pointer=0)])

    def test_longer_ability_list_and_following_numeric_field(self):
        data = packed_object(b"hfoo", b"h001", [(b"uabi",3,0,0,b"A001\0"),(b"uhpm",0,0,0,struct.pack("<i",150))])
        edits = []
        def prepare(uid, field, level, pointer, original, entry, kind, offset, token):
            value = "A001,A002" if kind==3 else 180
            edits.append(dict(id=uid,field=field,level=level,pointer=pointer,original=original,
                              entry=entry,kind=kind,offset=offset,value=value))
        list(decode_objects(data,"war3map.w3u",False,{},prepare))
        updated = object_edits(data,"war3map.w3u",edits)
        fields = list(decode_objects(updated,"war3map.w3u",False,{}))[0][2]
        self.assertEqual(fields["uabi",0,0].value,"A001,A002")
        self.assertEqual(fields["uhpm",0,0].value,180)

    def test_multiline_wts_change(self):
        data=b"STRING 1\r\n// Description: Hello\r\nworld (Tooltip)\r\n{\r\nHello\r\nworld\r\n}\r\n"
        edit=dict(id=1,original="Hello\nworld",value="New\ntext")
        result=wts_edits(data,"war3map.wts",[edit])
        self.assertEqual(result,data.replace(b"{\r\nHello\r\nworld",b"{\r\nNew\r\ntext"))

    def test_skin_identity_and_map_parent_merge(self):
        skin = packed_object(b"h001", bytes(4), [(b"unam",3,0,0,b"TRIGSTR_001\0")])
        unit = packed_object(b"hfoo", b"h001", [(b"uhpm",0,0,0,struct.pack("<i",0))])
        files = {"war3mapSkin.w3u":skin, "war3map.w3u":unit}
        wts = string_table(b"STRING 1\r\n// tooltip\r\n{\r\nFootman <&>\r\n}\r\n")
        fields = object_table(files.get, "w3u", wts)["h001"]
        self.assertEqual(fields["unam",0,0].value, "Footman <&>")
        self.assertEqual(fields["uhpm",0,0].value, 0)

    def test_line_edit_preserves_bom_endings_and_checks_original(self):
        data = b"\xef\xbb\xbf[Misc]\r\nScale=0.5\r\n"
        edit = dict(line=2, original="Scale=0.5", value="Scale=0.25")
        self.assertEqual(line_edits(data, "war3mapMisc.txt", [edit]), data.replace(b"0.5",b"0.25"))
        with self.assertRaises(ValueError):
            line_edits(data, "war3mapMisc.txt", [dict(edit, original="Scale=2")])

    def test_spawn_from_separately_registered_action(self):
        source = """globals
constant integer SPELL = 'A001'
endglobals
function Cast takes nothing returns boolean
return GetSpellAbilityId() == SPELL
endfunction
function Spawn takes nothing returns nothing
call CreateUnit(GetOwningPlayer(GetTriggerUnit()), 'h001', 0., 0., 0.)
endfunction
function Init takes nothing returns nothing
call TriggerAddCondition(t, Condition(function Cast))
call TriggerAddAction(t, function Spawn)
endfunction"""
        functions, _, ids, paths = script_index(source)
        self.assertEqual(functions["Spawn"]["creates"], ["h001"])
        self.assertIn("Cast", ids["A001"])
        self.assertEqual(paths["A001"], [{"unit":"h001", "path":["Cast","Spawn"]}])


if __name__ == "__main__":
    unittest.main()
