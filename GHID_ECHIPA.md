# Ghid Brewtality 3:16 — cum construim scrapere noi pentru peViitor.ro

Acest document e pentru oricine din echipă vrea să creeze un scraper nou
pentru o companie, pornind de la template-ul oficial **Brewtality 3:16**
(`github.com/peviitor-scrapers/Brewtality-3-16`). Nu trebuie să știi Node.js sau
Python în profunzime ca să-l folosești — dar trebuie să înțelegi logica de
mai jos ca să știi *ce* modifici când ceva nu merge din prima.

---

## 1. Ce e Brewtality 3:16 și de ce există

Fiecare companie de pe peViitor.ro (Antibiotice, Aerostar, Hochland etc.) are
propriul ei "scraper" — un mic program care intră periodic pe pagina de
cariere a companiei, extrage joburile deschise și le trimite către API-ul
peViitor (`api.peviitor.ro`), care le indexează în Solr.

Înainte, fiecare scraper nou se scria de la zero. Brewtality 3:16 e
**template-ul** care rezolvă asta: clonezi repo-ul, rulezi un script, răspunzi
la câteva întrebări despre companie, și în 2 minute ai un scraper complet
funcțional, cu teste, self-healing și workflow-uri GitHub Actions gata puse.

**Un lucru important:** Brewtality 3:16 (template-ul) și un scraper derivat
din el (ex. `antibiotice-sa-nodejs-scraper`) sunt **două produse separate**.
Modificările făcute direct pe un scraper derivat NU se propagă automat înapoi
în template — și invers, actualizările template-ului nu ajung automat la
scraperele deja create (asta e motivul pentru care unele repo-uri din fleet
au versiuni diferite ale template-ului, urmărite în `SCRAPERS.md`).

## 2. Ce limbaj aleg — JavaScript sau Python?

Template-ul are **două implementări complete și paralele**, cu exact aceeași
logică:

| | Stack | Teste |
|---|---|---|
| `scraper-js/` | Node.js + `node-fetch` + Cheerio + Jest | 200 teste |
| `scraper-py/` | Python 3.10+ + `requests` + BeautifulSoup + pytest (+ opțional [Scrapling](https://github.com/D4Vinci/Scrapling)) | 172 teste |

Nu contează cu care lucrezi mai bine — alege limbajul pe care îl cunoști sau
pe care restul echipei deja îl folosește pentru compania respectivă. Ambele
produc exact același rezultat: joburi trimise către `api.peviitor.ro`.

## 3. Cum creezi un scraper nou (pas cu pas)

```bash
# 1. Clonezi template-ul într-un folder nou, cu numele companiei
git clone https://github.com/peviitor-scrapers/Brewtality-3-16.git nume-companie-scraper
cd nume-companie-scraper

# 2. Rulezi scriptul interactiv (alege UNUL dintre cele două)
node setup.js
# SAU
python setup.py
```

Scriptul te întreabă, pe rând:

1. **JavaScript sau Python?** — `js` / `py` (sau `1` / `2`)
2. **Datele companiei**: nume legal (MAJUSCULE, ex. `ACME WIDGETS SRL`),
   brand comercial, CIF (fără prefixul `RO`), site web, URL-ul paginii de
   cariere, oraș sediu central
3. **(opțional)** îți propune să detecteze automat un selector CSS pentru
   joburi, făcând un fetch read-only pe pagina de cariere
4. **(opțional)** URL sitemap de joburi, prefixul URL-urilor canonice de job,
   cei 3 selectori CSS principali — poți lăsa goale toate astea și scraperul
   pornește doar cu fallback-urile generice (vezi secțiunea 4)
5. **Owner-ul și numele repo-ului GitHub** (ex. `TheTatu13` /
   `acme-widgets-nodejs-scraper`)

La final îți arată un rezumat și te întreabă `Apply?` — dacă răspunzi `y`,
scriptul rescrie folderul **pe loc**:

- șterge varianta de limbaj pe care n-ai ales-o (`scraper-py/` sau
  `scraper-js/`)
- șterge istoricul git al template-ului și `setup.js`/`setup.py`, apoi
  inițializează un repo git **nou și independent**, direct pe branch-ul
  `main`
- mută tot conținutul variantei alese la rădăcina folderului
- înlocuiește fiecare `{{PLACEHOLDER}}` cu răspunsurile tale
- setează numele pachetului (`package.json` / `pyproject.toml`)

```bash
# 3. Rulezi testele — trec imediat, chiar înainte să atingi vreun selector
npm install && npm run test:unit        # JS
pip install -e ".[dev]" && pytest -q    # Python

# 4. Primul commit
git add -A
git commit -m "Initial scraper for ACME WIDGETS SRL"

# 5. (opțional) Creezi repo-ul pe GitHub și dai push
gh repo create peviitor-scrapers/acme-widgets-nodejs-scraper --public --source=. --push
gh repo edit peviitor-scrapers/acme-widgets-nodejs-scraper \
  --add-topic job-seeker-ro-spider --add-topic peviitor-ro
```

Ghidul complet, cu o sesiune reală întreagă de exemplu (fiecare întrebare +
răspuns), e în [`TUTORIAL.md`](TUTORIAL.md) din repo.

## 4. Logica din spate — "self-healing cascade"

Asta e partea cea mai importantă de înțeles, pentru că e motivul pentru care
scraperele astea NU se strică de fiecare dată când o companie își schimbă
puțin site-ul.

Pentru fiecare câmp (titlul jobului, cardul de job, data limită), scraperul
încearcă mai multe strategii **în cascadă**, în ordine, până una întoarce un
rezultat:

| Nivel | Strategie |
|---|---|
| 1 | Selectorul CSS principal, configurat în `config/scraper.json` |
| 2 | Selectori CSS de rezervă (fallback) |
| 3 | Ancorare structurală — atribute `[itemprop]`, `[aria-label]`, `<meta content>`, sau bloc **JSON-LD `JobPosting`** (multe site-uri au datele astea ascunse în cod, independent de clasele CSS) |
| 4 | Regex direct pe HTML brut (ultimă soluție) |
| 5 *(doar Python, opțional)* | **Scrapling** — bibliotecă ce reține "amprenta" unui element și îl regăsește prin similaritate dacă selectorul CSS s-a schimbat |

Fiecare pas are propriul `try/catch` — dacă un pas eșuează sau se recuperează
printr-un fallback, se loghează **imediat**, ca să vezi în output-ul rulării
că ceva s-a schimbat pe site, nu peste două săptămâni când cineva întreabă de
ce nu mai apar joburi noi.

**Canary-ul**: dacă o rulare întreagă nu extrage niciun job (sau nimic nu
supraviețuiește validării), scraperul **oprește execuția înainte să scrie
orice** — fișier local sau request către API. O rulare cu 0 rezultate e
aproape mereu semn de HTML stricat, nu o companie fără joburi deschise.

Codul generic al cascadei (nu se atinge, doar site-specific se ajustează):

| Componentă | JS | Python |
|---|---|---|
| cascada de selectori | `scraper/self-healing.js` (`firstMatch`, `locateArticles`, `jsonLdJobPostings`) | `scraper/self_healing.py` (`first_match`, `locate_articles`, `json_ld_job_postings`) |
| validare + canary | `scraper/validate.js` | `scraper/validate.py` |
| retry / backoff | `scraper/api.js` (`fetchWithRetry`) | `scraper/fetch.py` |

Detalii complete: `scraper-js/ai/AGENTS.md` și `scraper-py/ai/SELF-HEALING.md`
(au și un tabel de paritate JS↔Python).

## 5. Ce fișiere modifici efectiv, pe scraperul derivat

După ce ai derivat scraperul, tot ce ai de făcut e specific site-ului:

1. **`scraper/config/scraper.json`** — aici pui selectorii CSS **reali** ai
   site-ului (cardul de job, titlul, meta/deadline). Lași fallback-urile
   generice sub ei, neatinse — sunt plasa de siguranță.
2. **`parseListing` din `scraper/index.js`** (JS) sau **`parse_listing` din
   `scraper/parse.py`** (Python) — funcția care ia HTML-ul paginii de cariere
   și scoate lista de joburi. Aici adaptezi logica dacă structura site-ului e
   neobișnuită (ex. paginare, joburi încărcate prin JS, API JSON ascuns în loc
   de HTML).
3. **Un test nou pentru fiecare nivel de fallback pe care îl adaugi** —
   uită-te în `tests/` la testele existente pentru cascada de self-healing ca
   model.

Ce **NU** se modifică manual: `self-healing.js`/`self_healing.py`,
`validate.js`/`validate.py`, `api.js`/`fetch.py` — astea sunt generice și
comune tuturor scraperelor din fleet. Dacă găsești un bug acolo, se repară în
template și apoi se propagă (manual, momentan) la scraperele existente.

## 6. Alte lucruri de reținut (din experiența fleet-ului real)

- **Preferă API-uri JSON ascunse în locul HTML-ului**, dacă site-ul are. Multe
  career-pages (Workday etc.) expun un endpoint JSON mult mai stabil decât
  clasele CSS — vezi exemplul `e-infra-sa-python-scraper`, care scrapuiește
  direct un board `applytojob.com` structurat.
- **Deduplicare**: cheia unică e URL-ul final al jobului (după orice
  redirect-uri), pentru că `url` e chiar `uniqueKey`-ul din Solr.
- **Retry**: backoff exponențial cu jitter, retry doar pe 429/500/502/503/504
  — nu pe 404/401/403 (alea sunt refuzuri reale, nu erori temporare).
- **GitHub Actions**: rulează pe cron (de obicei zilnic), ora e mereu UTC, iar
  GitHub nu garantează timing exact (poate întârzia 15+ min). Pe repo public,
  dacă nu există activitate 60 de zile, workflow-urile programate se
  dezactivează automat.
- **Dependabot**: fiecare repo din fleet are `dependabot.yml`, care deschide
  automat PR-uri când o dependență (npm/pip) are o versiune nouă. E normal să
  vezi din când în când un PR de tip `chore(deps): bump X from Y to Z` — nu e
  ceva ce ai stricat tu.

## 7. Testare — ce înseamnă "verde"

```bash
npm run test:unit          # rapid, fixtures generice, mereu trebuie să treacă
npm run test:integration   # are nevoie de site-ul real + ANAF + API-ul peViitor
npm run test:e2e
npm run test:consistency   # verifică README/config, are nevoie de GITHUB_TOKEN
```

Testele `unit` sunt singurele care trebuie să treacă mereu, indiferent de
context — folosesc fixtures generice, nu ating internetul. Cele de
`integration`/`e2e`/`consistency` se sar automat (skip) dacă nu au acces la
site-ul real, ANAF sau API-ul peViitor — asta e normal în CI dacă acele
servicii nu sunt disponibile din motive independente de codul tău.

## 8. Convenții de commit / PR

Repo-ul are `COMMIT_CHECKLIST.md` și `DEFINITION_OF_DONE.md` — citește-le
înainte de primul PR pe un scraper existent din fleet. Pe scurt:

- Un commit = o schimbare coerentă (nu amesteca fix de selector cu update de
  dependențe într-un singur commit)
- Rulează testele local înainte de push
- La un repo nou derivat, adaugă exact 2 topic-uri pe GitHub:
  `job-seeker-ro-spider` și `peviitor-ro`

## 9. Unde cauți mai multe detalii

- [`TUTORIAL.md`](TUTORIAL.md) — sesiune completă de exemplu, cu output real
  la fiecare pas
- [`README.md`](README.md) — referința tehnică completă (placeholders,
  cascada, structura de fișiere)
- [`ai/PROMPTS.md`](ai/PROMPTS.md) — prompt-uri gata făcute dacă lucrezi cu
  un agent AI (Claude Code etc.) pentru derivare, diagnosticare CI roșu,
  verificare self-healing
- [`SCRAPERS.md`](SCRAPERS.md) — registrul tuturor scraperelor active din
  fleet, cu versiunea de template și eventuale note speciale per companie

## 10. Când termini un scraper

Când un scraper e gata (derivat, testat, verde, push-uit) — dai un mesaj pe
serverul de Discord cu **"HellYeah"** 🍺, ca să știe toată echipa că mai avem
unul funcțional în fleet.

---

*Document scris pentru echipa peViitor.ro / Brewtality 3:16. Orice
neclaritate găsită aici → deschide un issue sau întreabă în Discord, ca să
actualizăm ghidul.*
