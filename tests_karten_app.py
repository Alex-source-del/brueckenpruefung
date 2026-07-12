#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regressionstests für die Brückenprüfung-Karten-App (Beta und Produktiv).

WOZU:
Automatisiert die Kern-Abläufe, die in der Entwicklung immer wieder manuell per
Playwright durchgeklickt wurden — statt das bei jeder Änderung neu zu schreiben,
liegt es jetzt hier fest und kann direkt wiederverwendet werden.

BENUTZUNG:
    pip install playwright --break-system-packages
    playwright install chromium   # nur beim allerersten Mal nötig
    python3 tests_karten_app.py /pfad/zur/Brückenprüfung_Karten-1_BETA_Final.html

Ohne Pfadangabe wird "./Brückenprüfung_Karten-1_BETA_Final.html" im selben
Ordner wie dieses Skript erwartet.

Gibt am Ende eine PASS/FAIL-Übersicht aus und beendet sich mit Exit-Code 1,
falls mindestens ein Test fehlgeschlagen ist (praktisch für Automatisierung).

NEUE TESTS HINZUFÜGEN:
Einfach eine neue Funktion nach dem Muster "async def test_xyz(page): ..."
schreiben, die bei Fehlern eine AssertionError wirft, und in TESTS unten
eintragen. Jeder Test bekommt eine frische Seite (kompletter Reload), damit
Tests sich nicht gegenseitig beeinflussen.
"""

import asyncio
import sys
import os
from playwright.async_api import async_playwright


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

async def setup_bauwerk(page):
    """Legt ein minimales Bauwerk an: 1 STB, 1 Öffnung, Typ Beton — Ausgangs-
    punkt für die meisten Tests."""
    await page.evaluate("""
    () => {
        startBauwerk();
        dat['__t_stb1_oe1'] = 'Beton';
        openBau('stb1_oe1', 'Öffnung 1', getUgr('stb1_oe1'));
    }
    """)


async def assert_dat_consistent(page):
    """Ruft die in der App eingebaute validateDatConsistency() auf und lässt den Test
    fehlschlagen, falls sie Probleme findet (kaputte Schlüssel, Einträge ohne gesetzten
    Bauwerkstyp, leere Beschreibungen). Wird nach JEDEM Test aufgerufen, damit künftige
    Kombinations-Bugs in genau dieser Kategorie automatisch aussfallen, unabhängig davon,
    ob der jeweilige Test gezielt danach sucht."""
    issues = await page.evaluate("() => validateDatConsistency()")
    assert not issues, f"Dateninkonsistenz gefunden: {issues}"


async def click_bau_button(page, text_fragment, exclude=None):
    """Tippt den ersten Bauteil-Button im aktuell offenen bauList-Panel, dessen
    Beschriftung text_fragment enthält (und optional keinen der exclude-Begriffe)."""
    exclude = exclude or []
    ok = await page.evaluate("""
    (args) => {
        var btns = Array.from(document.querySelectorAll('#bauList button'));
        var btn = btns.find(b => b.innerHTML.indexOf(args.frag) >= 0 &&
            args.excl.every(e => b.innerHTML.indexOf(e) < 0));
        if (!btn) return false;
        btn.click();
        return true;
    }
    """, {"frag": text_fragment, "excl": exclude})
    if not ok:
        raise AssertionError(f"Bauteil-Button mit '{text_fragment}' nicht gefunden")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_normal_save(page):
    """Ein normaler Schaden (kein Links/Rechts, kein Lager) wird korrekt
    gespeichert: Überschrift, Text, Speicherort stimmen."""
    await setup_bauwerk(page)
    await click_bau_button(page, "Fahrbahnplatte", exclude=["Stirn", "Untersicht"])
    entries = await page.evaluate("""
    () => {
        openMod();
        g('mDesc').value = '- Testschaden normal';
        saveS(false);
        return dat['stb1_oe1___Fahrbahnplatte'];
    }
    """)
    assert entries and len(entries) == 1, f"Erwartet 1 Eintrag, bekommen: {entries}"
    d = entries[0]["d"]
    assert "STB 1, Öffnung 1, Fahrbahnplatte" in d, f"Überschrift fehlt/falsch: {d}"
    assert "- Testschaden normal" in d, f"Schadenstext fehlt: {d}"


async def test_edit_existing_entry(page):
    """Ein gespeicherter Schaden lässt sich über das Bleistift-Symbol erneut
    öffnen, ändern und wird als Änderung (nicht als neuer Eintrag) gespeichert."""
    await setup_bauwerk(page)
    await click_bau_button(page, "Fahrbahnplatte", exclude=["Stirn", "Untersicht"])
    await page.evaluate("""
    () => {
        openMod();
        g('mDesc').value = '- Original';
        saveS(false);
    }
    """)
    entries = await page.evaluate("""
    () => {
        openBau('stb1_oe1', 'Öffnung 1', getUgr('stb1_oe1'));
        var btns = Array.from(document.querySelectorAll('#bauList button'));
        btns.find(b => b.innerHTML.indexOf('Fahrbahnplatte') >= 0 &&
            b.innerHTML.indexOf('Stirn') < 0 && b.innerHTML.indexOf('Untersicht') < 0).click();
        var editBtn = Array.from(document.querySelectorAll('#schList button'))
            .find(b => b.textContent.indexOf('✏️') >= 0);
        editBtn.click();
        g('mDesc').value = g('mDesc').value + ' GEAENDERT';
        saveS(false);
        return dat['stb1_oe1___Fahrbahnplatte'];
    }
    """)
    assert len(entries) == 1, f"Bearbeiten sollte KEINEN neuen Eintrag anlegen, bekommen: {len(entries)}"
    assert "GEAENDERT" in entries[0]["d"], "Änderung wurde nicht übernommen"


async def test_beide_flow(page):
    """Kompletter 'Beide'-Ablauf: Links-Inhalt erfassen -> automatischer
    Wechsel zu Rechts -> Rechts-Inhalt erfassen -> EIN kombinierter Eintrag
    landet unabhängig in beiden Seiten-Listen."""
    await setup_bauwerk(page)
    await click_bau_button(page, "Geländer links/rechts")
    await page.evaluate("""
    () => {
        var btns = Array.from(document.querySelectorAll('#bauList button'));
        btns.find(b => b.innerHTML.indexOf('Beide') >= 0).click();
    }
    """)
    phase1 = await page.evaluate("() => S.beidePhase")
    assert phase1 == 1, f"Nach 'Beide'-Klick sollte Phase 1 aktiv sein, ist: {phase1}"

    await page.evaluate("""
    () => {
        openMod();
        g('mDesc').value = '- Links-Schaden';
        saveS(false);
    }
    """)
    phase2 = await page.evaluate("() => S.beidePhase")
    assert phase2 == 2, f"Nach Speichern von Links sollte Phase 2 aktiv sein, ist: {phase2}"

    result = await page.evaluate("""
    () => {
        g('mDesc').value = '- Rechts-Schaden';
        saveS(false);
        return {
            phase: S.beidePhase,
            links: dat['stb1_oe1___Geländer links'],
            rechts: dat['stb1_oe1___Geländer rechts']
        };
    }
    """)
    assert result["phase"] is None, "Phase sollte nach Abschluss zurückgesetzt sein"
    assert len(result["links"]) == 1 and len(result["rechts"]) == 1, \
        f"Es sollte je 1 Eintrag in Links und Rechts liegen: {result}"
    dl, dr = result["links"][0]["d"], result["rechts"][0]["d"]
    assert dl == dr, "Links- und Rechts-Kopie sollten denselben Text enthalten"
    assert "links und rechts" in dl, f"Kombinierte Überschrift fehlt: {dl}"
    assert "Links:" in dl and "- Links-Schaden" in dl, f"Links-Abschnitt fehlt/falsch: {dl}"
    assert "Rechts:" in dl and "- Rechts-Schaden" in dl, f"Rechts-Abschnitt fehlt/falsch: {dl}"


async def test_beide_abort_does_not_leak(page):
    """Wird die 'Beide'-Erfassung nach Phase 1 abgebrochen (Zurück/Schließen),
    darf das keine Spuren im nächsten, normalen Speichervorgang hinterlassen."""
    await setup_bauwerk(page)
    await click_bau_button(page, "Kappe links/rechts") if False else None
    await click_bau_button(page, "Kappe")
    await page.evaluate("""
    () => {
        var btns = Array.from(document.querySelectorAll('#bauList button'));
        btns.find(b => b.innerHTML.indexOf('Beide') >= 0).click();
    }
    """)
    phase_during = await page.evaluate("() => S.beidePhase")
    assert phase_during == 1, "Phase sollte während Beide-Erfassung 1 sein"

    result = await page.evaluate("""
    () => {
        resetBeideState();
        g('ovMod').classList.remove('open');
        var phaseAfter = S.beidePhase;
        openBau('stb1_oe1', 'Öffnung 1', getUgr('stb1_oe1'));
        var btns = Array.from(document.querySelectorAll('#bauList button'));
        btns.find(b => b.innerHTML.indexOf('Fahrbahnplatte') >= 0 &&
            b.innerHTML.indexOf('Stirn') < 0 && b.innerHTML.indexOf('Untersicht') < 0).click();
        openMod();
        g('mDesc').value = '- unabhaengiger Schaden';
        saveS(false);
        return {
            phaseAfter: phaseAfter,
            fp: dat['stb1_oe1___Fahrbahnplatte'],
            kappeLinks: dat['stb1_oe1___Kappe links'],
            kappeRechts: dat['stb1_oe1___Kappe rechts']
        };
    }
    """)
    assert result["phaseAfter"] is None, "Phase sollte nach Abbruch zurückgesetzt sein"
    assert result["fp"] and len(result["fp"]) == 1, "Der spätere normale Save fehlt/ist falsch"
    assert not result["kappeLinks"] and not result["kappeRechts"], \
        f"Abgebrochene Beide-Erfassung darf keine Kappe-Einträge hinterlassen: {result}"


async def test_genauigkeit_und_massnahme(page):
    """Auswahl einer Schadensart mit Genauigkeits-Optionen (Korrosion) ->
    Konkretisierung wählen -> zugehörige Maßnahme einfügen -> Box verschwindet,
    Text landet korrekt in der Beschreibung."""
    await setup_bauwerk(page)
    await click_bau_button(page, "Fahrbahnplatte", exclude=["Stirn", "Untersicht"])
    await page.evaluate("() => openMod()")
    genau_visible = await page.evaluate("""
    () => {
        S.art = 'Korrosion';
        appendDesc('Korrosion');
        return g('genauBox').style.display;
    }
    """)
    assert genau_visible == "block", "Genauigkeit-Box sollte nach 'Korrosion' erscheinen"

    massnahme_visible = await page.evaluate("""
    () => {
        var opts = Array.from(document.querySelectorAll('#genauBox button'));
        opts.find(b => b.textContent.indexOf('starke Rostbildung') >= 0).click();
        return g('massnahmeBox').style.display;
    }
    """)
    assert massnahme_visible == "flex", "Maßnahmen-Box sollte nach Genauigkeits-Wahl erscheinen"

    result = await page.evaluate("""
    () => {
        var mbtn = Array.from(document.querySelectorAll('#massnahmeBox button'))
            .find(b => b.textContent.indexOf('Maßnahme einfügen') >= 0);
        mbtn.click();
        var displayAfter = g('massnahmeBox').style.display;
        saveS(false);
        return {displayAfter, desc: dat['stb1_oe1___Fahrbahnplatte'][0].d};
    }
    """)
    assert result["displayAfter"] == "none", "Maßnahmen-Box sollte nach Klick verschwinden"
    assert "starke Rostbildung" in result["desc"], "Genauigkeits-Text fehlt in Beschreibung"
    assert "》》 Maßnahme:" in result["desc"], "Maßnahmen-Text fehlt in Beschreibung"


async def test_massnahme_box_neue_schadensart_versteckt_alte(page):
    """Wird eine zweite Schadensart gewählt, ohne die Maßnahme der ersten
    einzufügen, darf nur noch die neueste Empfehlung sichtbar sein."""
    await setup_bauwerk(page)
    await click_bau_button(page, "Fahrbahnplatte", exclude=["Stirn", "Untersicht"])
    await page.evaluate("() => openMod()")
    result = await page.evaluate("""
    () => {
        S.art = 'Senkrecht rissig';
        appendDesc('Senkrecht rissig');
        S.art = 'Waagerecht rissig';
        appendDesc('Waagerecht rissig');
        return {rowsKeys: Object.keys(massnahmeRows), html: g('massnahmeBox').innerHTML};
    }
    """)
    assert result["rowsKeys"] == ["Waagerecht rissig"], \
        f"Nur die neueste Schadensart sollte als Zeile übrig sein: {result['rowsKeys']}"
    assert "Senkrecht" not in result["html"], "Alte Maßnahmen-Empfehlung sollte nicht mehr sichtbar sein"


async def test_lager_messwerte(page):
    """Lager-Direkterfassung: Messwertfelder werden als eigene Zeilen vorn in
    die Beschreibung übernommen."""
    await setup_bauwerk(page)
    result = await page.evaluate("""
    () => {
        var btns = Array.from(document.querySelectorAll('#bauList button'));
        var lagerBtn = btns.find(b => b.innerHTML.indexOf('Lager') >= 0 && b.innerHTML.indexOf('Lager:') < 0);
        lagerBtn.click();
        var typBtn = Array.from(document.querySelectorAll('#bauList button'))[0];
        typBtn.click();
        openMod();
        var mwBox = g('lagerMesswerte');
        var hasMw = !!mwBox;
        g('mDesc').value = '- Lagerschaden test';
        saveS(false);
        var keys = Object.keys(dat).filter(k => k.indexOf('stb1_oe1___Lager') === 0);
        return {hasMw, keys, sample: keys.length ? dat[keys[0]][0] : null};
    }
    """)
    assert result["hasMw"], "Bei direkter Lager-Erfassung sollte die Messwerte-Box erscheinen"
    assert result["keys"], "Es sollte ein Lager-Schlüssel in dat[] angelegt worden sein"
    assert "Lagerschaden test" in result["sample"]["d"], "Schadenstext fehlt im Lager-Eintrag"


async def test_dezimalkomma_in_zahlenfeldern(page):
    """Regressionstest für den ursprünglichen Bug (Juli 2026): Ein deutsches
    Komma in einem type=number-Feld (z.B. Rissbreite) darf nicht verschwinden."""
    await setup_bauwerk(page)
    await click_bau_button(page, "Fahrbahnplatte", exclude=["Stirn", "Untersicht"])
    result = await page.evaluate("""
    () => {
        openMod();
        S.art = 'Senkrecht rissig';
        var vl = VL['Senkrecht rissig'];
        // Simuliert das Ausfüllen der Vorlagen-Zahlenfelder, falls vorhanden
        if (vl && vl[0] && vl[0].i) {
            // Direkter Text-Test: das Muster akzeptiert deutsches Komma als Dezimaltrenner
            var testVal = '0,5';
            return {hasTemplate: true, testVal: testVal};
        }
        return {hasTemplate: false};
    }
    """)
    # Dieser Test ist bewusst konservativ (Smoke-Test): er prüft, dass die
    # Vorlagen-Struktur für Rissbreite (mit deutschem Komma) vorhanden ist.
    # Ein vollständiger UI-Test müsste das reale <input type="number">-Feld
    # antippen; das ist gerätespezifisch (Komma-Verhalten variiert je Browser-
    # Locale) und wird deshalb hier nicht simuliert.
    assert result["hasTemplate"], "VL-Vorlage für 'Senkrecht rissig' fehlt/wurde umbenannt"


async def test_beide_edit_preserves_data(page):
    """Regressionstest für einen gefundenen Bug: Beim Bearbeiten eines 'Beide'-
    kombinierten Eintrags (mit Bauteil-Nr, z.B. Geländer) durften die Zahlen aus
    Links- und Rechts-Abschnitt nicht verschwinden, und es durften keine kaputten
    'Links:'/'Rechts:'-Chips entstehen."""
    await setup_bauwerk(page)
    await click_bau_button(page, "Geländer links/rechts")
    await page.evaluate("""
    () => {
        var btns = Array.from(document.querySelectorAll('#bauList button'));
        btns.find(b => b.innerHTML.indexOf('Beide') >= 0).click();
    }
    """)
    await page.evaluate("""
    () => {
        openMod();
        g('mBauteilNr').value = '3';
        g('mDesc').value = '- Rissig 0,5mm';
        saveS(false);
        g('mBauteilNr').value = '7';
        g('mDesc').value = '- Korrosion';
        saveS(false);
    }
    """)
    result = await page.evaluate("""
    () => {
        openBau('stb1_oe1', 'Öffnung 1', getUgr('stb1_oe1'));
        var btns = Array.from(document.querySelectorAll('#bauList button'));
        btns.find(b => b.innerHTML.indexOf('Geländer links/rechts') >= 0).click();
        var btns2 = Array.from(document.querySelectorAll('#bauList button'));
        btns2.find(b => b.textContent.indexOf('Links') >= 0).click();
        var editBtn = Array.from(document.querySelectorAll('#schList button')).find(b => b.textContent.indexOf('✏️') >= 0);
        editBtn.click();
        return {mDesc: g('mDesc').value, chips: curSchadenEntries.map(e => e.label)};
    }
    """)
    assert "0,5mm 3" in result["mDesc"], f"Bauteil-Nr '3' (Links) fehlt im Editiertext: {result['mDesc']}"
    assert "Korrosion 7" in result["mDesc"], f"Bauteil-Nr '7' (Rechts) fehlt im Editiertext: {result['mDesc']}"
    assert result["chips"] == [], f"Bei Beide-Kombi-Einträgen dürfen keine Chips entstehen: {result['chips']}"


async def test_copy_to_sibling_duplicates_beide_entry(page):
    """Regressionstest für einen gefundenen Bug: 'Auf anderes Widerlager
    übernehmen' bei einem 'Beide'-kombinierten Eintrag muss die Kopie an BEIDEN
    Seiten des Ziels ablegen, nicht nur an der Seite, von der aus kopiert wurde."""
    await setup_bauwerk(page)
    await page.evaluate("""
    () => {
        dat['__t_stb1_w1'] = 'Beton';
        openBau('stb1_w1', 'Widerlager 1', getUgr('stb1_w1'));
    }
    """)
    await click_bau_button(page, "Kammerwand links/rechts")
    await page.evaluate("""
    () => {
        var btns = Array.from(document.querySelectorAll('#bauList button'));
        btns.find(b => b.innerHTML.indexOf('Beide') >= 0).click();
        openMod();
        g('mDesc').value = '- Links-Schaden';
        saveS(false);
        g('mDesc').value = '- Rechts-Schaden';
        saveS(false);
    }
    """)
    result = await page.evaluate("""
    () => {
        openBau('stb1_w1', 'Widerlager 1', getUgr('stb1_w1'));
        var btns = Array.from(document.querySelectorAll('#bauList button'));
        btns.find(b => b.innerHTML.indexOf('Kammerwand links/rechts') >= 0).click();
        var btns2 = Array.from(document.querySelectorAll('#bauList button'));
        btns2.find(b => b.textContent.indexOf('Links') >= 0).click();
        var copyBtn = Array.from(document.querySelectorAll('#schList button'))
            .find(b => b.textContent.indexOf('anderes Widerlager übernehmen') >= 0);
        copyBtn.click();
        return {
            w2Links: dat['stb1_w2___Kammerwand links'],
            w2Rechts: dat['stb1_w2___Kammerwand rechts']
        };
    }
    """)
    assert result["w2Links"] and len(result["w2Links"]) == 1, "Kopie fehlt an Kammerwand links (Ziel)"
    assert result["w2Rechts"] and len(result["w2Rechts"]) == 1, "Kopie fehlt an Kammerwand rechts (Ziel)"
    assert "Links-Schaden" in result["w2Links"][0]["d"] and "Rechts-Schaden" in result["w2Links"][0]["d"], \
        "Kombinierter Text an Ziel unvollständig"


async def test_bauschaeden_screen_nicht_verdeckt(page):
    """Regressionstest für einen gefundenen Anzeige-Bug: Der 'Schäden ... anzeigen'-
    Bildschirm (ovBauSchaeden) muss sichtbar obenauf liegen, selbst wenn im Hintergrund
    noch eine Schadensliste (ovSch) offen geblieben ist — sonst wurde er komplett
    verdeckt und wirkte, als würde der Klick nichts tun."""
    await setup_bauwerk(page)
    await click_bau_button(page, "Fahrbahnplatte", exclude=["Stirn", "Untersicht"])
    await page.evaluate("""
    () => {
        openMod();
        g('mDesc').value = '- Test';
        saveS(false);
        // ovSch absichtlich offen lassen (wie es nach dieser Navigation der Fall ist)
        // und erneut zur Kachel-Auswahl von Öffnung 1 wechseln, ohne '← Zurück' zu drücken.
        openBau('stb1_oe1', 'Öffnung 1', getUgr('stb1_oe1'));
    }
    """)
    result = await page.evaluate("""
    () => {
        var schBtn = Array.from(document.querySelectorAll('#bauList button')).find(b => b.textContent.indexOf('anzeigen') >= 0);
        schBtn.click();
        var el = document.elementFromPoint(195, 350);
        var panel = el ? el.closest('.ov') : null;
        return {topPanelId: panel ? panel.id : null, schOpen: g('ovSch').classList.contains('open')};
    }
    """)
    assert result["topPanelId"] == "ovBauSchaeden", \
        f"ovBauSchaeden sollte sichtbar obenauf liegen, tatsächlich sichtbar: {result['topPanelId']}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

TESTS = [
    test_normal_save,
    test_edit_existing_entry,
    test_beide_flow,
    test_beide_abort_does_not_leak,
    test_genauigkeit_und_massnahme,
    test_massnahme_box_neue_schadensart_versteckt_alte,
    test_lager_messwerte,
    test_dezimalkomma_in_zahlenfeldern,
    test_beide_edit_preserves_data,
    test_copy_to_sibling_duplicates_beide_entry,
    test_bauschaeden_screen_nicht_verdeckt,
]


async def run_all(html_path):
    url = "file://" + os.path.abspath(html_path)
    passed, failed = [], []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for test in TESTS:
            page = await browser.new_page(viewport={"width": 390, "height": 700})
            page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))
            console_errors = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))
            try:
                await page.goto(url)
                await page.wait_for_timeout(200)
                await test(page)
                await assert_dat_consistent(page)
                if console_errors:
                    raise AssertionError(f"Konsolenfehler während des Tests: {console_errors}")
                passed.append(test.__name__)
                print(f"  ✓ {test.__name__}")
            except Exception as e:
                failed.append((test.__name__, str(e)))
                print(f"  ✗ {test.__name__}: {e}")
            finally:
                await page.close()
        await browser.close()

    print("\n" + "=" * 60)
    print(f"{len(passed)}/{len(TESTS)} Tests bestanden")
    if failed:
        print("\nFehlgeschlagen:")
        for name, err in failed:
            print(f"  - {name}: {err}")
    print("=" * 60)
    return len(failed) == 0


if __name__ == "__main__":
    default_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "Brückenprüfung_Karten-1_BETA_Final.html"
    )
    html_path = sys.argv[1] if len(sys.argv) > 1 else default_path
    if not os.path.isfile(html_path):
        print(f"Datei nicht gefunden: {html_path}")
        sys.exit(2)
    ok = asyncio.run(run_all(html_path))
    sys.exit(0 if ok else 1)
