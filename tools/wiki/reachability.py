"""Build directed gameplay relationships and retain evidence for each traversal."""
from collections import defaultdict, deque
import re


TYPES = {"abilCode":"abilities", "abilityList":"abilities", "heroAbilityList":"abilities",
         "abilitySkinList":"abilities", "unitCode":"units", "unitList":"units", "unitSkinList":"units",
         "itemList":"items", "buffList":"effects", "effectList":"effects",
         "upgradeList":"upgrades", "upgradeCode":"upgrades"}
LABELS = {"uhab":"Hero abilities", "uabi":"Abilities", "iabi":"Item abilities", "abuf":"Buffs",
          "aeff":"Effects", "useu":"Units sold", "usei":"Items sold", "utra":"Units trained",
          "uupt":"Upgrades to", "upgr":"Upgrades used", "ubui":"Structures built"}


def callable_functions(functions):
    def walk(blocked):
        seen = set()
        queue = deque(["main", "config"])
        while queue:
            name = queue.popleft()
            if name in functions and name not in seen:
                seen.add(name)
                queue.extend(n for n in functions[name]["calls"] if n not in blocked.get(name,()))
        return seen

    possible = walk({})
    uses = defaultdict(list)
    for name in possible:
        for line in functions[name]["body"].splitlines():
            line = line.partition("//")[0]
            for handle in set(re.findall(r"\bgg_trg_\w+",line)):
                uses[handle].append((name,line))
    blocked = defaultdict(set)
    for name in possible:
        body = functions[name]["body"]
        for handle in re.findall(r"set\s+(gg_trg_\w+)\s*=\s*CreateTrigger\(\)",body):
            conds = re.findall(r"TriggerAddCondition\(\s*"+handle+r"\s*,\s*Condition\(\s*function\s+(\w+)",body)
            # World Editor emits an unconditional first guard for disabled GUI conditions.
            impossible = any(re.match(r"[^\n]+\n\s*(?:return false\s*\n\s*endfunction|if\s*\(\s*not\s*\(\s*(?:false\s*==\s*true|true\s*==\s*false)\s*\)\s*\)\s*then\s*return false\b)",
                                      functions.get(n,{}).get("body","")) for n in conds)
            external = [line for n,line in uses[handle] if n!=name]
            known = re.compile(r"\b(?:EnableTrigger|DisableTrigger|IsTriggerEnabled|DestroyTrigger|ConditionalTriggerExecute|TriggerExecute(?:BJ)?|TriggerEvaluate|TriggerRegister\w*)\(\s*"+handle+r"\b")
            escaped = any(not known.search(line) for line in external)
            references = "\n".join(line for _,line in uses[handle])
            forced = re.search(r"\bTriggerExecute(?:BJ)?\(\s*"+handle+r"\b",references)
            conditional = re.search(r"\bConditionalTriggerExecute\(\s*"+handle+r"\b",references)
            enabled = re.search(r"\bEnableTrigger\(\s*"+handle+r"\b",references)
            disabled = re.search(r"\bDisableTrigger\(\s*"+handle+r"\b",body)
            if escaped or forced or not (impossible or (disabled and not enabled and not conditional)):
                continue
            register = r"TriggerAddAction\(\s*"+handle+r"\s*,\s*function\s+(\w+)\s*\)"
            other_code = re.sub(register,"",body)
            for action in re.findall(register,body):
                if not re.search(r"\b"+action+r"\b",other_code):
                    blocked[name].add(action)
    return walk(blocked)


def spell_actions(funcs, live):
    """Follow spell checks into their registered actions, helpers and callbacks."""
    actions = defaultdict(set)
    for name in live:
        code = funcs[name]["body"]
        conditions = re.findall(r"TriggerAddCondition\(\s*(\w+)\s*,\s*(?:Condition|Filter)\(\s*function\s+(\w+)",code)
        handlers = re.findall(r"TriggerAddAction\(\s*(\w+)\s*,\s*function\s+(\w+)",code)
        for trigger, condition in conditions:
            todo, seen = [condition], set()
            while todo:
                n = todo.pop()
                if n in funcs and n not in seen:
                    seen.add(n)
                    todo.extend(funcs[n]["calls"])
            for n in seen:
                if funcs[n]["spells"]:
                    actions[n].update(h for t,h in handlers if t==trigger)
    owners = defaultdict(set)
    for name in sorted(live):
        if not funcs[name]["spells"]:
            continue
        queue, seen = deque([name,*actions[name]]), set()
        while queue:
            n=queue.popleft()
            if n in live and n not in seen:
                seen.add(n)
                owners[n].update(funcs[name]["spells"])
                queue.extend(funcs[n]["calls"])
    return owners


def colossal(db, live, root):
    functions = db["functions"]
    init = "Trig_colossal_stats_Actions"
    if init not in live or "Trig_colossal_spawn_Actions" not in live:
        return {}
    configs = defaultdict(dict)
    for field, index, rhs in re.findall(r"set udg_colossal_unit_(\w+)\[(\d+)\]\s*=\s*('....'|[-\d.]+)",
                                       functions[init]["body"]):
        configs[int(index)][field] = rhs.strip("'") if rhs.startswith("'") else float(rhs)
    # Only slots used by a spawn entry supply gameplay units.
    slots = [(slot, int(r["id"])) for slot, r in configs.items() if "id" in r]
    settings = functions["Trig_colossal_variables_Actions"]["body"]
    def setting(key):
        match = re.search(r"set udg_" + key + r"\s*=\s*(\d+(?:\.\d+)?)", settings)
        return float(match[1]) if match else None
    spawn_name = "F8_SpawnColo" if "F8_SpawnColo" in live else "Trig_colossal_spawn_Actions"
    spawn = functions[spawn_name]["body"]
    dispatcher = functions["Trig_colossal_spawn_Actions"]["body"]
    parity = {}
    if spawn_name == "F8_SpawnColo":
        loop = re.search(r"set entry\s*=\s*(\d+)[\s\S]*?exitwhen entry\s*>\s*(\d+)", dispatcher)
        bosses = re.search(r"local integer big\s*=\s*(\d+)[\s\S]*?if ModuloInteger\(udg_colossal_wave,\s*2\)\s*==\s*0 then\s*set big\s*=\s*(\d+)", dispatcher)
        if bosses and "F8_SpawnColo(big," in dispatcher:
            parity = {int(bosses[1]): "odd", int(bosses[2]): "even"}
            if loop:
                slots = [(s,i) for s,i in slots if s in parity or int(loop[1]) <= s <= int(loop[2])]
    else:
        cond = "Trig_colossal_spawn_Func005C"
        check = functions.get(cond, {}).get("body", "")
        if re.search(r"ModuloReal\(I2R\(udg_colossal_wave\),\s*2(?:\.0+)?\)\s*==\s*0", check):
            branch = re.search(cond+r"\(\).*?then\s+(.*?)\belse\b(.*?)\bendif\b", dispatcher, re.S)
            if branch:
                for side, text in zip(("even","odd"), branch.groups()):
                    selected = re.search(r"set udg_X_colo\s*=\s*(\d+)",text)
                    if selected:
                        parity[int(selected[1])] = side
    scaled = [field for field in ("hp", "dmg", "bounty") if re.search(
        r"set udg_colossal_unit_"+field+r"_actual[^\n]*="+r"[^\n]*_base[^\n]*\+[^\n]*_base[^\n]*\*[^\n]*udg_colossal_wave[^\n]*\*[^\n]*udg_colossal_difficulty", spawn)]
    level = re.search(r"return\s+(\d+)\s*\+\s*IMinBJ\((\d+),\s*\(wave-1\)/(\d+)\)",
                      functions.get("SyncColoLevel", {}).get("body",""))
    max_wave = re.search(r"set udg_colossal_max_wave\s*=\s*(\d+)",functions.get("Trig_init_Actions",{}).get("body",""))
    result = {}
    for slot, index in slots:
        row = configs.get(index, {})
        if "type" not in row:
            continue
        key = "units/"+row["type"]
        root(key, "Colossal wave roster", init)
        rec = result.setdefault(key, {"entries":[], "rules":[init, spawn_name, "Trig_colossal_variables_Actions"]})
        rec["entries"].append({"slot":slot, "base":row})
        if slot <= 2:
            rec.update(boss=True, growth=setting("colossal_difficulty"), scaled=scaled,
                       first=setting("t_colossal_initial"), interval=setting("t_colossal_reoccuring"))
            if max_wave and "Trig_init_Actions" in live:
                rec["max_wave"] = int(max_wave[1])
                rec["rules"].append("Trig_init_Actions")
            if slot in parity:
                rec["parity"] = parity[slot]
                if spawn_name != "Trig_colossal_spawn_Actions":
                    rec["rules"].append("Trig_colossal_spawn_Actions")
            if level and "SyncColoLevel(" in spawn:
                rec["level_curve"] = list(map(int,level.groups()))
                rec["rules"].append("SyncColoLevel")
    return result


def summoned_units(funcs, live, edge):
    """Bind summon-event actions to the type tests registered for that trigger."""
    result = defaultdict(list)
    for init in sorted(live):
        body = funcs[init]["body"]
        if "EVENT_PLAYER_UNIT_SUMMON" not in body:
            continue
        conditions = re.findall(r"TriggerAddCondition\(\s*(\w+)\s*,\s*Condition\(\s*function\s+(\w+)",body)
        for trigger, action in re.findall(r"TriggerAddAction\(\s*(\w+)\s*,\s*function\s+(\w+)",body):
            if action not in live:
                continue
            todo = [n for handle,n in conditions if handle==trigger]
            seen,units=set(),set()
            while todo:
                n=todo.pop()
                if n in funcs and n not in seen:
                    seen.add(n)
                    units.update(re.findall(r"GetUnitTypeId\(\s*GetSummonedUnit\(\)\s*\)\s*==\s*'(\w{4})'",funcs[n]["body"]))
                    todo.extend(funcs[n]["calls"])
            if not units:
                continue
            code=funcs[action]["body"]
            aliases={"GetSummonedUnit()"}
            ranks=[]
            values=defaultdict(dict)
            for line in code.splitlines():
                line=line.strip()
                assignment=re.search(r"\b(\w+(?:\[\w+\])?)\s*=\s*(.+)",line)
                if assignment and assignment[2].strip() in aliases:
                    aliases.add(assignment[1])
                if line.startswith(("if ","elseif ")):
                    if line.startswith("elseif ") and ranks:
                        ranks.pop()
                    predicate=line
                    helper=re.search(r"\b(\w+)\(\)",line)
                    if helper and helper[1] in funcs:
                        predicate=funcs[helper[1]]["body"]
                    rank=re.search(r"\budg_abilitylevel\s*==\s*(\d+)",predicate)
                    ranks.append(int(rank[1]) if rank else 0)
                elif line=="else" and ranks:
                    ranks[-1]=0
                elif line=="endif" and ranks:
                    ranks.pop()
                for ability,target in re.findall(r"(?:UnitAddAbilityBJ|SetUnitAbilityLevelSwapped)\(\s*'(\w{4})'\s*,\s*(\w+(?:\[\w+\])?)",line):
                    if target in aliases:
                        for uid in sorted(units):
                            edge("units/"+uid,"abilities/"+ability,"Abilities on summon",action,
                                 next((v for v in reversed(ranks) if v),0))
                setting=re.fullmatch(r"set\s+udg_summon_(\w+)\[(\d+)\]\s*=\s*(-?[\d.]+)",line)
                if setting and re.search(r"\budg_summon_"+setting[1]+r"\[udg_abilitylevel\]",code):
                    values[setting[1]][int(setting[2])]=float(setting[3])
            source_spell=re.search(r"set\s+udg_abilitylevel\s*=\s*GetUnitAbilityLevelSwapped\(\s*'(\w{4})'",code)
            for uid in sorted(units):
                key="units/"+uid
                if source_spell:
                    edge("abilities/"+source_spell[1],key,"Summon scaling",action)
                result[key].append({"action":action,"values":values})
    return result


def creation_contexts(fn, funcs, owners):
    """Resolve temporary spawn arrays at their use site, respecting branch-local writes."""
    sites = {line for line, _, uid in fn["creation_sites"] if not uid}
    if not sites:
        return {}
    code = fn["body"]
    aliases = set(re.findall(r"\b(\w+)\s*=\s*GetSpellAbilityId\(\)",code))
    aliases.add("GetSpellAbilityId()")
    spell_var = "|".join(re.escape(v) for v in sorted(aliases))
    context, guards, writes, result = [], [], defaultdict(list), {}
    for line_no, line in enumerate(code.splitlines(),fn["line"]):
        line = line.partition("//")[0].strip()
        if line.startswith(("if ", "elseif ")) or line == "else":
            if not line.startswith("if ") and context:
                context.pop()
                guards.pop()
            context.append(line_no)
            predicate = line
            helper = re.search(r"\b(\w+)\(\)",line)
            if helper and helper[1] in funcs:
                predicate = funcs[helper[1]]["body"]
            ids = set(re.findall(r"\b(?:"+spell_var+r")\s*==\s*'(\w{4})'",predicate))
            guards.append(ids & owners)
        if line=="endif" and context:
            context.pop()
            guards.pop()
        assign = re.search(r"\b(\w+)(?:\[(\d+)\])?\s*=\s*'(\w{4})'",line)
        if assign:
            writes[assign[1]].append((tuple(context),assign[2],assign[3]))
        if line_no not in sites:
            continue
        spells = next((g for g in reversed(guards) if g),owners)
        resolved = {}
        for var, assignments in writes.items():
            # A direct write in this branch supersedes the same slot's earlier value.
            slots = {}
            for branch, index, uid in assignments:
                if tuple(context[:len(branch)]) == branch:
                    slots[index] = uid
            if slots:
                candidates = list(slots.items())
            else:
                # A table initialized under an earlier guard (e.g. on first cast).
                candidates = [(index,uid) for _,index,uid in assignments]
            pool = defaultdict(set)
            for index,uid in candidates:
                if index is None:
                    pool[uid]
                else:
                    pool[uid].add(int(index))
            resolved[var] = pool
        result[line_no] = (spells,resolved)
    return result


def trace(db):
    objects, funcs = db["objects"], db["functions"]
    live = callable_functions(funcs)
    roots, edges, unresolved = defaultdict(list), defaultdict(dict), []
    ids = defaultdict(list)
    for key, obj in objects.items():
        ids[obj["id"]].append(key)
    def root(key, reason, source):
        if key in objects and [reason,source] not in roots[key]:
            roots[key].append([reason,source])
    def edge(a,b,label,source,level=0,reference_only=False):
        if a not in objects or b not in objects or a==b:
            return
        item = edges[a].setdefault((b,label), {"to":b,"label":label,"levels":[],"sources":[],
                                                "reference_only":reference_only})
        if level and level not in item["levels"]:
            item["levels"].append(level)
        if source not in item["sources"]:
            item["sources"].append(source)
    for key, o in objects.items():
        family = key.partition("/")[0]
        cap = next((int(float(s["value"])) for s in o["stats"] if s["field"]=="alev"), 0)
        for f in o["linked_fields"]:
            if cap and f["level"]>cap:
                continue
            field = f["field"]
            value_type = db["metadata"].get(family,{}).get(field,{}).get("type")
            target_type = TYPES.get(value_type)
            reference_only = value_type in {"techList","unitSkinList","abilitySkinList"} or field in {"udep","urva","icid"}
            label = LABELS.get(field, f["label"])
            for uid in f["ids"]:
                keys = [target_type+"/"+uid] if target_type else ids[uid]
                if not any(k in objects for k in keys):
                    unresolved.append([key,field,uid])
                for k in keys:
                    edge(key,k,label,f["source"],f["level"],reference_only)
    for rec in db["placements"]:
        types = ("items","units") if rec["entry"]=="war3mapUnits.doo" else ("doodads","destructibles")
        for group in types:
            owner = group+"/"+rec["id"]
            root(owner,"Placed on the map",rec["entry"])
            for drops in rec.get("drop_sets",[]):
                for drop in drops:
                    edge(owner,"items/"+drop["item"],"Drops",rec["entry"])
            for field,target,group2 in [("inventory","item","items"),("ability_settings","ability","abilities"),
                                        ("random_units","unit","units")]:
                for record in rec.get(field,[]):
                    edge(owner,group2+"/"+record[target],field.replace("_"," ").title(),rec["entry"])
    def random_table(group, table_id, reason):
        for t in db["settings"].get("random_"+group+"_tables",[]):
            if t["index"]==table_id:
                for row in t["sets"]:
                    for uid in ([r["item"] for r in row] if group=="item" else row["ids"]):
                        root(group+"s/"+uid,reason,"war3map.w3i")
    for rec in db["placements"]:
        if rec.get("item_table",-1)>=0:
            random_table("item",rec["item_table"],"Placed drop table")
        if rec.get("random_mode")==1:
            random_table("unit",rec["random_table"],"Random placement")

    table = {t["key"]:t for t in db["tables"]}
    hero_limit = re.findall(r"set udg_total_hero_count\s*=\s*(\d+)",funcs.get("Trig_set_hero_numbers_Actions",{}).get("body",""))
    excluded = set(re.findall(r"\bheroType\s*==\s*'(.{4})'",funcs.get("SoloFootsIsNoMuteHeroType",{}).get("body","")))
    if "Trig_set_hero_numbers_Actions" in live and any("udg_hero_type[" in funcs[n]["body"] for n in live if re.search("Draft|Stock|Tavern|Pick",n)):
        for r in table.get("heroes",{}).get("rows",[]):
            if r["id"] and r["id"]["value"] not in excluded and (not hero_limit or r["index"]["value"]<=int(hero_limit[-1])):
                root("units/"+r["id"]["value"],"Hero selection roster",r["id"]["source"])
    if "Trig_set_spawn_variables_Actions" in live:
        for row in table.get("spawns",{}).get("rows",[]):
            if row.get("udg_base_type") and row["id"]:
                base = "units/"+row["udg_base_type"]["value"]
                root(base,"Troop production base",row["udg_base_type"]["source"])
                edge(base,"units/"+row["id"]["value"],"Spawns",row["id"]["source"])
    waves = colossal(db,live,root)
    summon_rules = summoned_units(funcs,live,edge)
    paths = defaultdict(set)
    for spell, records in db["creation_paths"].items():
        for p in records:
            if all(n in live for n in p["path"]):
                edge("abilities/"+spell,"units/"+p["unit"],"Scripted summon"," → ".join(p["path"]))
                paths[p["path"][-1]].add(p["unit"])

    dynamic = []
    assignments = defaultdict(set)
    indexed = defaultdict(lambda:defaultdict(set))
    for _,line in db["globals"]:
        match=re.fullmatch(r"\s*(?:constant\s+)?integer\s+(\w+)\s*=\s*'(\w{4})'\s*",line)
        if match:
            assignments[match[1]].add(match[2])
    uses = []
    spells = spell_actions(funcs, live)
    for name in sorted(live):
        fn = funcs[name]
        code = "\n".join(line.partition("//")[0] for line in fn["body"].splitlines())
        contexts = creation_contexts(fn,funcs,spells[name])
        for var,index,uid in re.findall(r"(?m)^\s*set\s+(\w+)(?:\[([^\n=]+)\])?\s*=\s*'(.{4})'",code):
            if index or var.startswith("udg_") or var in assignments:
                assignments[var].add(uid)
            if index.isdigit():
                indexed[var][uid].add(int(index))
        for line, expr, uid in fn["creation_sites"]:
            if uid:
                for spell in spells[name]:
                    edge("abilities/"+spell,"units/"+uid,"Scripted summon",f"{name}:{line}")
                if uid not in paths[name] and not spells[name] and "preload" not in name.lower():
                    root("units/"+uid,"Created by trigger",f"{name}:{line}")
            else:
                dynamic.append([name,line,expr])
                match = re.fullmatch(r"(\w+)(?:\[(.+)\])?",expr)
                if match:
                    owners, pools = contexts[line]
                    uses.append((match[1],"units",name,match[2] or "",owners,pools.get(match[1])))
        for native, group in (("CreateItem","items"),("UnitAddItemByIdSwapped","items"),("AddItemToStockBJ","items"),
                              ("AddUnitToStockBJ","units"),("ReplaceUnitBJ","units"),("AddItemToStock","items"),
                              ("AddUnitToStock","units"),("UnitAddItemById","items")):
            second = native in {"ReplaceUnitBJ","AddItemToStock","AddUnitToStock","UnitAddItemById"}
            for match in re.finditer(r"\b"+native+r"\(\s*"+(r"[^,\n]+,\s*" if second else "")+r"(?:'(.{4})'|(\w+)\[)",code):
                uid,var = match.groups()
                if uid:
                    if not (fn["consumes"] and uid in fn["grants"]):
                        root(group+"/"+uid,"Trigger stock, reward or replacement",name)
                elif var:
                    uses.append((var,group,name,"",spells[name],None))
        # Associate grants with their unit-type guard, including nested tech checks.
        aliases = dict(re.findall(r"\b(\w+)\s*=\s*GetUnitTypeId\((\w+)\)",code))
        guards = []
        spawned_vars = {}
        sites = {number:uid for number,_,uid in fn["creation_sites"]}
        last = None
        for number,line in enumerate(code.splitlines(),fn["line"]):
            line = line.strip()
            if number in sites:
                last = sites[number]
            assigned = re.search(r"\b(\w+)\s*=\s*(.+)",line)
            if assigned:
                var, rhs = assigned.groups()
                if number in sites or rhs.startswith("GetLastCreatedUnit()"):
                    spawned_vars[var]=last
                else:
                    spawned_vars.pop(var,None)
            if line.startswith(("if ","elseif ")):
                if line.startswith("elseif ") and guards:
                    guards.pop()
                pairs = re.findall(r"(GetUnitTypeId\(\w+\)|\w+)\s*==\s*'(\w{4})'",line)
                guards.append([(aliases.get(v,v.removeprefix("GetUnitTypeId(").removesuffix(")")),uid)
                               for v,uid in pairs if v in aliases or v.startswith("GetUnitTypeId(")])
            elif line=="else" and guards:
                guards[-1]=[]
            elif line=="endif" and guards:
                guards.pop()
            for tech in re.findall(r"(?:GetPlayerTechCountSimple\(\s*|GetPlayerTechCount\([^,\n]+,\s*)'(\w{4})'",line):
                for guard in guards:
                    for _,uid in guard:
                        edge("units/"+uid,"upgrades/"+tech,"Upgrade checks",name)
            grants = re.findall(r"UnitAddAbility\(\s*(\w+)\s*,\s*'(.{4})'",line)
            grants += [(target,ability) for ability,target in re.findall(r"UnitAddAbilityBJ\(\s*'(.{4})'\s*,\s*(\w+)",line)]
            for target,ability in grants:
                if spawned_vars.get(target):
                    edge("units/"+spawned_vars[target],"abilities/"+ability,"Triggered abilities",name)
                for guard in guards:
                    for unit,uid in guard:
                        if unit==target:
                            edge("units/"+uid,"abilities/"+ability,"Triggered abilities",name)
    for var,group,name,index,owners,local_pool in uses:
        if var in {"udg_hero_type","udg_spawn_unit","udg_colossal_unit_type"}:
            continue  # The indexed rosters above retain their availability and owner.
        for uid in sorted(local_pool if local_pool is not None else assignments[var]):
            if owners:
                for spell in owners:
                    ranks=(local_pool if local_pool is not None else indexed[var])[uid] if re.search("level|rank|lvl",index,re.I) else ()
                    for rank in sorted(ranks) or [0]:
                        edge("abilities/"+spell,group+"/"+uid,"Possible summons" if group=="units" else "Possible rewards",name+" / "+var,rank)
            else:
                root(group+"/"+uid,"Trigger selection table",name+" / "+var)
    for rec in db["recipes"]:
        if rec["fn"] in live:
            for a in rec["consumes"]:
                for b in rec["grants"]:
                    edge("items/"+a,"items/"+b,"Crafting results",rec["fn"])
    for k,r in waves.items():
        for uid in re.findall(r"set udg_colossal_dropped_item\[\d+\]\s*=\s*'(.{4})'",funcs["Trig_colossal_variables_Actions"]["body"]):
            if r.get("boss"):
                edge(k,"items/"+uid,"Wave loot pool","Trig_colossal_variables_Actions")
    graph = {}
    for key, outgoing in edges.items():
        graph[key] = sorted(outgoing.values(),key=lambda e:(e["label"],e["to"]))
        for e in graph[key]:
            e["levels"].sort()
            e["sources"].sort()
    seen = {}
    queue = deque((k,None) for k in sorted(roots))
    while queue:
        k, parent = queue.popleft()
        if k not in seen:
            seen[k]=parent
            queue.extend((v["to"],k) for v in graph.get(k,())
                         if not v["reference_only"] and v["to"] not in seen)
    parents = set()
    for key in seen:
        k=key
        while k in objects:
            base = k.partition("/")[0]+"/"+objects[k]["parent"]
            if base==k or base in parents or base not in objects:
                break
            parents.add(base)
            k=base
    visual = defaultdict(set)
    for key in seen:
        for path in objects[key].get("visuals",[]):
            model = re.sub(r"\.mdl$", ".mdx", path.replace("/","\\").replace("\\\\","\\").lower())
            if model in db["models"]:
                visual[model].add(key)
    for model, m in db["models"].items():
        for owner, source in m["uses"]:
            if owner.startswith("fn/"):
                for spell in spells.get(owner[3:], ()):
                    if "abilities/"+spell in seen:
                        visual[model].add("abilities/"+spell)
    supporting = {v["to"] for key in seen for v in edges.get(key,{}).values() if v["reference_only"]}
    return {"roots":roots,"via":seen,"support":sorted(supporting-set(seen)),"edges":graph,
            "parents":sorted(parents-set(seen)), "waves":waves, "summon_rules":summon_rules,
            "unresolved":sorted(set(map(tuple,unresolved))),
            "dynamic":dynamic,"functions":sorted(live),"visuals":{m:sorted(keys) for m,keys in visual.items()}}
