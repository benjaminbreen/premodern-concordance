#!/usr/bin/env python3
"""
Apply expert-reviewed member splits to concordance.json.

Each entry in SPLITS was individually reviewed by analyzing:
- The cluster's canonical name and modern identification
- The member's name, source book, context, and string similarity scores
- Whether the member is a legitimate cross-language translation or a genuinely different entity

Members that are cross-language translations (e.g. "eau" for water, "corpo" for body,
"tripas" for intestines) are KEPT. Only members referring to genuinely different entities
are split out.
"""

import json
import copy
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "web" / "public" / "data" / "concordance.json"

# (cluster_id, member_name) -> reason for split
# Each was individually reviewed against the cluster's canonical concept
SPLITS = {
    # pedras (Calculus/kidney stones) — "roches" = geological rocks, not medical calculus
    (5, "roches"): "rocks/geological formations, not kidney stones",

    # agua (Water) — "rcaux" = currency unit; "riccio" = sugar candy
    (17, "rcaux"): "currency unit (réaux), not water",
    (17, "riccio"): "sugar candy, not water",

    # Ciatica (Sciatica) — "Catarros" = catarrh, completely different disease
    (52, "Catarros"): "catarrh (cold), not sciatica",

    # madre (Dura mater) — "mammas" = breasts, different anatomy
    (60, "mammas"): "breasts of dugongs, not dura mater",

    # ar (air) — multiple false matches due to short cluster name
    (78, "arratel"): "unit of weight (arratel), not air",
    (78, "arpens"): "unit of land measurement (arpent), not air",
    (78, "arphait"): "substance from Dead Sea (asphalt?), not air",
    (78, "goma arabia"): "gum arabic, not air",

    # cor (Cordial) — "corzimento" = cooking/digestion
    (89, "corzimento"): "cooking/digestion process (cozimento), not cordial",

    # Nitro (Saltpeter) — "nilã" = lapis lazuli/sapphire
    (93, "nilã"): "sapphire/lapis lazuli, not saltpeter",

    # réis (Real currency) — multiple unrelated matches
    (97, "riisias"): "type of fabric, not currency",
    (97, "ragia"): "resin/turpentine, not currency",
    (97, "rayo"): "condition/vapor, not currency",

    # tristeza (Sadness) — "terciárias" = tertian fever
    (101, "terciárias"): "tertian fever type, not sadness",

    # mercadores (Merchants) — "Commerson" = naturalist
    (111, "Commerson"): "Philibert Commerson, naturalist, not a merchant",

    # olio (oil) — "oolithes" = oolitic limestone
    (125, "oolithes"): "oolitic limestone (geological), not oil",

    # cap. (Chapter reference) — multiple unrelated matches
    (148, "caxas"): "boxes for sugar/treasuries, not chapter references",
    (148, "cabane"): "small dwelling, not chapter reference",

    # Calicut (Kozhikode) — three unrelated places
    (149, "Coraçone"): "different Indian region (Coromandel?), not Calicut",
    (149, "Corientes"): "Cape Corrientes, not Calicut",
    (149, "Corcovado"): "coastal peak (Corcovado), not Calicut",

    # hortela (Mint) — "orraca" = palm sap spirit
    (154, "orraca"): "distilled palm sap spirit (arrack), not mint",

    # calamo aromático (Acorus Calamus) — "Hyera" = purgative; "hetre" = food for sick
    (158, "Hyera"): "Hiera (purgative compound), not calamus",
    (158, "hetre"): "food for the sick, not calamus",

    # Capricorn — "Escorpião" = Scorpio zodiac sign
    (203, "Escorpião"): "Scorpio zodiac sign, not Capricorn",

    # Thymo (Thyme) — "tomat" = tomato
    (210, "tomat"): "tomato, not thyme",

    # tabaschir (Tabasheer/bamboo sugar) — "tabac torcido" = rolled tobacco
    (248, "tabac torcido"): "rolled tobacco product, not tabasheer (bamboo sugar)",

    # turibitti (Turpeth) — "turritclics" = turritella fossil
    (276, "turritclics"): "turritella fossil in limestone, not turpeth",

    # monçam (Monsoon) — "Monſtris" = monsters; "mas" = Portuguese "but"
    (280, "Monſtris"): "monsters (topic of cited work), not monsoon",
    (280, "mas"): "Portuguese word 'but', not monsoon",

    # caricuru (Gold) — unrelated matches
    (293, "kichuris"): "food for horses, not gold",
    (293, "Carabe"): "amber/ambergris remedy, not gold",

    # tornillo (screw press) — "trombeta" = trumpet
    (298, "trombeta"): "trumpet/shell instrument, not screw press",

    # ovo (Egg) — "ovelhas" = sheep
    (310, "ovelhas"): "sheep (animal), not egg",

    # pedra (Calculus) — "contaram" = verb, noise
    (316, "contaram"): "verb/noise word, not calculus",

    # Eryfipela (erysipelas) — "Eſcrophulas" = scrofula
    (332, "Eſcrophulas"): "scrofula, different disease from erysipelas",

    # Fistula's — "fástios" = fasting/loss of appetite
    (341, "fástios"): "fasting/loss of appetite, not fistula",

    # Panama — "Pemba" = African island
    (345, "Pemba"): "Pemba Island (Africa), not Panama",

    # Quinaquina (Cinchona) — "Quinces" = quince fruit
    (350, "Quinces"): "quince fruit, not cinchona/quinine",

    # ardores (Burning sensation) — "Carde" = twisting disease
    (387, "Carde"): "disease causing twisting, not burning sensation",

    # trachyte — "tartaro" = tartar (dental/wine deposit)
    (409, "tartaro"): "tartar (chemical/dental deposit), not trachyte rock",

    # Rhewm (Phlegm) — "renum" = kidney
    (413, "renum"): "kidney (renum), not phlegm",

    # rofmaninho (Rosemary) — two unrelated plants
    (444, "Espique"): "spikenard (Espique), not rosemary",
    (444, "Espes"): "different plant, not rosemary",

    # cabrito (Kid goat) — "carabe" = amber/ambergris
    (451, "carabe"): "amber/ambergris substance, not kid goat",

    # papoulas (Poppy) — "Rhewn" = unclear/different plant
    (453, "Rhewn"): "different plant species, not poppy",

    # funcho (Fennel) — "ferula" = giant fennel (different genus, produces galbanum)
    (454, "ferula"): "Ferula (giant fennel/asafoetida), different genus from fennel",

    # feu volcanique — "feus" = Latin pronoun
    (488, "feus"): "Latin pronoun 'suis', not volcanic activity",

    # redness — "raucedine" = hoarseness
    (490, "raucedine"): "hoarseness (raucedine), not redness",

    # Timor — "Tayrona" = Sierra Nevada peak in Colombia
    (493, "Tayrona"): "Tayrona (Colombia), not Timor",

    # excrementos (Excrement) — "escrupulos" = unit of weight
    (504, "escrupulos"): "scruple (unit of weight), not excrement",

    # Moçambique — two unrelated places
    (513, "Motagua"): "Motagua River (Central America), not Mozambique",
    (513, "Moluques"): "Moluccas (Indonesia), not Mozambique",

    # Cotopaxi — "Cotamaluquo" = Indian region
    (520, "Cotamaluquo"): "Golconda/Cotalmaluco (India), not Cotopaxi volcano",

    # Thibet (Tibet) — "Taïti" = Tahiti
    (522, "Taïti"): "Tahiti (Pacific island), not Tibet",

    # Cocomero (Watermelon) — "Coumarouma" = tonka bean
    (538, "Coumarouma"): "Coumarouma (tonka bean tree), not watermelon",

    # Been bianco (White beans) — "blanco" = white sugar
    (574, "blanco"): "white sugar, not white beans",

    # crusados (Cruisado coin) — "croix" = cross
    (619, "croix"): "cross (religious object), not cruisado coin",

    # Margarita (Pearl) — "Aleffandrino" = alexandrine substance
    (628, "Aleffandrino"): "alexandrine substance, not pearl",

    # mordaz (acrid) — "mollesse" = softness
    (643, "mollesse"): "softness (opposite of acrid), not acrid",

    # Ortiz — "Oríxá" = Orissa (India)
    (645, "Oríxá"): "Orissa/Odisha (India), not Ortiz (Venezuela)",

    # Jeru (Jericho) — "Jezreel" = different city
    (659, "Jezreel"): "Jezreel (different biblical city), not Jericho",

    # Dandrif (Dandruff) — "damarefia" = nausea condition
    (676, "damarefia"): "condition causing nausea, not dandruff",

    # Oxus (Amu Darya) — "Ozark" = Ozark Mountains
    (689, "Ozark"): "Ozark Mountains (North America), not Oxus/Amu Darya",

    # Nurses — "Nurcino" = lithotomist surgeon
    (719, "Nurcino"): "lithotomist surgeon (from Norcia), not a nurse",

    # corado (Reddish complexion) — "cator" = heat
    (745, "cator"): "heat (calor), not reddish complexion",

    # nacidas (Boils) — "Freekles" = freckles
    (747, "Freekles"): "freckles (skin discoloration), not boils",

    # Ava — "Avidi" = Monts Abibe
    (778, "Avidi"): "Monts Abibe, not Ava (Myanmar)",

    # estoraque (Storax) — "torchis" = building material
    (805, "torchis"): "torchis (building material), not storax resin",

    # expectoraçao (Expectoration) — "excrecencias" = growths
    (839, "excrecencias"): "excrescences/growths, not expectoration",

    # Leaõ (Lion) — "Leech" = leech (bloodletting creature)
    (842, "Leech"): "leech (annelid for bloodletting), not lion",

    # MU e uma noites (1001 Nights) — "noite" = generic "night"
    (847, "noite"): "generic 'night', not the book 1001 Nights",

    # houiller (Coal) — "Hieiro" = iron
    (851, "Hieiro"): "iron (hierro), not coal",

    # San Fernando — "San Filippe" = different place
    (875, "San Filippe"): "San Filippo (different place), not San Fernando",

    # pão (Bread) — "lacre de pão" = lac in cake form
    (905, "lacre de pão"): "lac/lacquer in cake form, not bread",

    # Sack (sack wine) — "sukku" = dried ginger
    (936, "sukku"): "dried ginger (Sanskrit name), not sack wine",

    # Nearcho (Nearchus) — "Neighbors" = generic term
    (942, "Neighbors"): "generic 'neighbors', not Nearchus the admiral",

    # kala (Banana) — "kelte" = language family
    (977, "kelte"): "Celtic language family, not banana",

    # fangrados (Phlebotomy) — "fanões" = currency
    (978, "fanões"): "fanão (coin), not phlebotomy",

    # coando-se (Cervix mucus) — "couvade" = ritual
    (997, "couvade"): "couvade ritual, not cervix mucus",

    # Nifperos (quince) — "nenufaro" = water lily
    (1008, "nenufaro"): "nenúfar (water lily), not quince",

    # Cerracca (Lac) — "Ceruicabras" = hybrid creature
    (1012, "Ceruicabras"): "cervicabra (hybrid creature), not lac",

    # mambum (Arenga pinnata) — "mamillo" = nipple/cauterization
    (1029, "mamillo"): "mamillo/nipple, not arenga palm",

    # meçuá — "minhacaſa" = "my house"
    (1035, "minhacaſa"): "'my house' (minha casa), not a place name",

    # bengali (Bengali language) — "banharſe" = bathing
    (1038, "banharſe"): "bathing (bañarse), not Bengali language",

    # Lyão (Lyon) — "Lyſia" = Lisbon
    (1041, "Lyſia"): "Lisbon (Lysia), not Lyon",

    # ficymas (phlegm) — "fireixos" = ash trees
    (1069, "fireixos"): "ash trees (freixos), not phlegm",

    # Horn-Church (Hornchurch) — "Horn" = Cape Horn
    (1081, "Horn"): "Cape Horn (navigation), not Hornchurch",

    # Dog-wood — "DOGE" = title/plant
    (1091, "DOGE"): "doge (title), not dogwood plant",
}


def apply_splits(data):
    """Remove mismatched members from clusters."""
    # Build lookup: cid -> cluster index
    cid_map = {c["id"]: i for i, c in enumerate(data)}

    removed_count = 0
    affected_clusters = set()

    for (cid, member_name), reason in SPLITS.items():
        if cid not in cid_map:
            print(f"  SKIP: cluster {cid} not found")
            continue

        idx = cid_map[cid]
        cluster = data[idx]
        original_len = len(cluster["members"])

        # Remove matching members (case-sensitive exact match on name)
        cluster["members"] = [
            m for m in cluster["members"]
            if m["name"] != member_name
        ]

        n_removed = original_len - len(cluster["members"])
        if n_removed > 0:
            removed_count += n_removed
            affected_clusters.add(cid)
            print(f"  SPLIT: '{member_name}' from [{cid}] {cluster['canonical_name']} — {reason}")

            # Recompute stats
            if cluster["members"]:
                cluster["total_mentions"] = sum(m["count"] for m in cluster["members"])
                cluster["num_sources"] = len(set(m["book_id"] for m in cluster["members"]))
            else:
                cluster["total_mentions"] = 0
                cluster["num_sources"] = 0

            # Remove edges involving this member
            cluster["edges"] = [
                e for e in cluster.get("edges", [])
                if e.get("source") != member_name and e.get("target") != member_name
            ]
        else:
            # Try case-insensitive match
            lower_name = member_name.lower()
            cluster["members"] = [
                m for m in data[idx]["members"]
                if m["name"].lower() != lower_name
            ]
            n_removed = original_len - len(cluster["members"])
            if n_removed > 0:
                removed_count += n_removed
                affected_clusters.add(cid)
                print(f"  SPLIT (case-insensitive): '{member_name}' from [{cid}] {cluster['canonical_name']} — {reason}")
                if cluster["members"]:
                    cluster["total_mentions"] = sum(m["count"] for m in cluster["members"])
                    cluster["num_sources"] = len(set(m["book_id"] for m in cluster["members"]))
                else:
                    cluster["total_mentions"] = 0
                    cluster["num_sources"] = 0
                cluster["edges"] = [
                    e for e in cluster.get("edges", [])
                    if e.get("source", "").lower() != lower_name and e.get("target", "").lower() != lower_name
                ]
            else:
                print(f"  MISS: '{member_name}' not found in [{cid}] {cluster['canonical_name']}")

    # Remove clusters that ended up empty
    empty_before = len(data)
    data[:] = [c for c in data if c["members"]]
    empty_removed = empty_before - len(data)

    return removed_count, len(affected_clusters), empty_removed


def main():
    print(f"Loading {DATA}...")
    with open(DATA) as f:
        root = json.load(f)

    # Handle both flat list and {clusters: [...]} structure
    if isinstance(root, dict) and "clusters" in root:
        data = root["clusters"]
    else:
        data = root
        root = None

    print(f"  {len(data)} clusters loaded")

    # Backup
    backup = DATA.with_suffix(".json.bak3")
    with open(backup, "w") as f:
        json.dump(root if root is not None else data, f, ensure_ascii=False)
    print(f"  Backup saved to {backup}")

    print(f"\nApplying {len(SPLITS)} expert-reviewed splits...")
    removed, affected, emptied = apply_splits(data)

    print(f"\n--- Summary ---")
    print(f"  Members removed: {removed}")
    print(f"  Clusters affected: {affected}")
    print(f"  Empty clusters removed: {emptied}")
    print(f"  Final cluster count: {len(data)}")

    out = root if root is not None else data
    if root is not None:
        root["clusters"] = data
    with open(DATA, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"\nSaved to {DATA}")


if __name__ == "__main__":
    main()
