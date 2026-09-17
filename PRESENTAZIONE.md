# Presentazione e demo — scaletta

**Formato richiesto** (istruzioni del corso, slide 5): **10–15 minuti di slide, limite rigido** +
**5 minuti di demo live**. Obiettivo: **13 minuti di slide**, due di margine per le interruzioni.

**Scadenza.** L'Option 2 vale fino al **30 settembre 2026**. Prima serve la mail con oggetto
`[DM] Project Discussion` e le slide in allegato, più il link al repository; il prof risponde
fissando l'appuntamento o chiedendo miglioramenti. La mail va mandata **appena le slide sono pronte**.

Convenzione del documento: il **testo delle slide è in inglese**, come il report e il materiale del
corso; le **note del relatore sono in italiano**. Tutti i numeri vengono da `PROJECT_REPORT.md`
(soglia di riferimento ≥1.000 voti, salvo dove indicato) e sono verificati.

Il consiglio del corso da tenere a mente: *«put your focus on the content, not on the tool»*.
Quindi niente slide su Docker o sulle librerie Python: il tempo va a **domanda, metodo, risultati,
perché**.

---

## Scaletta

| # | Slide | Tempo | Cumulato |
|---|---|---:|---:|
| 1 | Title | 0:15 | 0:15 |
| 2 | The question | 0:45 | 1:00 |
| 3 | Dataset | 1:00 | 2:00 |
| 4 | Two models of the same data | 1:30 | 3:30 |
| 5 | Making the comparison valid | 1:30 | 5:00 |
| 6 | Four queries, four shapes | 1:00 | 6:00 |
| 7 | Q1 — SQL vs Cypher | 1:30 | 7:30 |
| 8 | Q1 — the ratio is a curve | 1:30 | 9:00 |
| 9 | Q2 and Q4 | 1:00 | 10:00 |
| 10 | Q3 — where PostgreSQL wins | 1:15 | 11:15 |
| 11 | What the checks caught | 0:45 | 12:00 |
| 12 | Conclusions | 1:00 | 13:00 |
| — | **Demo** | 5:00 | 18:00 |

Se si è in ritardo, **la slide 11 si comprime a una frase** e la 9 si fonde con la 8. Le slide
**8 e 10 non si tagliano**: sono il risultato e la sua controprova.

---

## Slide 1 — Title · 0:15

**Sulla slide**
> **PostgreSQL vs Neo4j on the IMDb dataset**
> Relational and graph models on the same analytical questions
> Lorenzo Ventrone (1802393) · Francesco Macrì (2055851)
> Data Management 2025/2026 — Sapienza Università di Roma

**Note:** nessuna. Si passa subito alla domanda.

---

## Slide 2 — The question · 0:45

**Sulla slide**
> Same data. Same questions. Two data models.
> **When does the shape of a query decide which database is faster — and by how much?**
>
> - PostgreSQL 15 — normalised relational schema, SQL
> - Neo4j 5.12 — property graph, Cypher

**Note:** «Non vogliamo stabilire quale database sia migliore: è una domanda senza risposta.
Vogliamo capire **per quale forma di query** uno dei due modelli ha un vantaggio, e se quel
vantaggio è un fattore costante o cresce con i dati. È la seconda parte che rende interessante il
risultato.»

---

## Slide 3 — Dataset · 1:00

**Sulla slide**
> IMDb non-commercial datasets: `title.basics`, `title.ratings`, `title.principals`, `name.basics`
>
> Filters: movies only · released after 1990 · **three vote thresholds**
>
> | | ≥10,000 votes | ≥1,000 votes | ≥100 votes |
> |---|---:|---:|---:|
> | Titles | 10,118 | 36,711 | 104,931 |
> | Persons | 79,281 | 268,541 | 664,143 |
> | Person–title links | 218,720 | 738,170 | 1,925,448 |

**Note:** «La soglia di voti serve a due cose: tenere film con un rating significativo e,
soprattutto, **ottenere tre dimensioni dello stesso dataset**. Misurare a una sola dimensione ci
avrebbe dato un numero; a tre ci dà una curva, e vedremo che è la curva a contenere il risultato.»

Da sapere se chiedono: `title.akas` non è usato, perché le traduzioni dei titoli non servono a
nessuna query.

---

## Slide 4 — Two models of the same data · 1:30

**Sulla slide** — due diagrammi affiancati.

> **Relational** — 5 tables
> `Titles` · `Persons` · `Genres` · `Title_Genres` · `Title_Principals (tconst, nconst, ordering, category)`
>
> **Graph**
> `(:Person)-[:ACTED_IN]->(:Title)` · `(:Person)-[:DIRECTED]->(:Title)`
> `(:Person)-[:WORKED_ON {category}]->(:Title)` · `(:Title)-[:HAS_GENRE]->(:Genre)`
>
> Role = relationship type in the graph → **index on `category` in SQL**, to level the field

**Note:** «Nel grafo il ruolo è il tipo di relazione, quindi filtrare per attori non costa nulla.
In SQL è una colonna, e senza un indice PostgreSQL partirebbe svantaggiato per una ragione che non
ha niente a che vedere con il modello. Per questo c'è un indice composito
`(category, tconst, nconst)`. **Abbiamo pareggiato le condizioni, non cambiato il concorrente.**»

---

## Slide 5 — Making the comparison valid · 1:30

**Sulla slide**
> **Three invariants, checked mechanically**
> 1. **Same data** — `verify_counts.py` compares both databases after every load; a mismatch stops the pipeline
> 2. **Same question** — role filters explicit in both languages; same depth limit on paths
> 3. **Same answer** — every run compares the two result sets **row by row**; a difference fails the benchmark
>
> **Measurement** — 2 warm-ups · 10 timed runs · median · alternating order · plans saved (`EXPLAIN ANALYZE`, `PROFILE`)

**Note:** «Il rischio più grande in un confronto così non è il codice lento, è **confrontare due
domande diverse senza accorgersene**. Due tempi su due risultati diversi non sono un confronto.
Il confronto riga per riga ha trovato due errori veri, che mostro alla fine.»

Da sapere se chiedono: ogni query ha la chiave primaria come ultimo criterio di ordinamento. In Q4
le posizioni 9 e 10 escono da **dieci film a pari merito**: senza tie-break il confronto
fallirebbe a caso.

---

## Slide 6 — Four queries, four shapes · 1:00

**Sulla slide**
> | | Question | Shape |
> |---|---|---|
> | Q1 | Degrees of separation between two actors | **deep traversal** |
> | Q2 | Most connected actors | **global aggregate** over a self-join |
> | Q3 | Average rating by genre, 2010s | **warehouse aggregation** |
> | Q4 | Films sharing the most cast & crew with *The Matrix* | **local 2-hop neighbourhood** |

**Note:** «Le quattro query non sono state scelte a caso: coprono quattro forme diverse. Tenete a
mente la colonna di destra, perché è quella che spiega i risultati.»

---

## Slide 7 — Q1: SQL vs Cypher · 1:30

**Sulla slide** — le due query affiancate (versione senza commenti: `demo.py` → `t`).

> **Cypher** — 3 lines, `shortestPath` over `ACTED_IN*..8`
> **SQL** — recursive CTE, two self-joins per level
>
> A recursive CTE **cannot keep a global visited set** → already-reached actors are expanded again at every level

**Note:** «In Cypher il cammino minimo è un operatore del linguaggio. In SQL la BFS l'abbiamo
scritta noi: `WITH RECURSIVE` fornisce la ricorsione, non l'attraversamento di un grafo. Il suo
limite è strutturale: nella parte ricorsiva si vede solo l'iterazione corrente, non l'insieme dei
nodi già visitati. Un attore raggiunto a distanza 1 viene espanso di nuovo a distanza 2, 3, 4.
Non è un difetto della nostra query, è un limite del modello dichiarativo.»

Tre cause del divario, da distinguere se chiedono (STUDIO.md §8):
1. nessun visited set (**linguaggio**);
2. ricerca unidirezionale contro bidirezionale (**algoritmo**);
3. discesa di B-tree contro dereference (**storage**, l'unica che si chiama *index-free adjacency*).

---

## Slide 8 — Q1: the ratio is a curve · 1:30 ⭐

**Sulla slide** — grafico con la distanza in ascissa, il tempo in scala logaritmica in ordinata, e
le due serie per soglia. In alternativa questa tabella, in grande:

> | Distance 4 | ≥10,000 | ≥1,000 | ≥100 |
> |---|---:|---:|---:|
> | PostgreSQL | 610 ms | 1.85 s | **4.47 s** |
> | Neo4j | 1.6 ms | 1.8 ms | **1.6 ms** |
> | Ratio | 390× | 1,051× | **2,834×** |
>
> At distance 1: **tie** (0.6–0.7 ms both, every size)
>
> Distance 4, ≥1,000: **2,311,600 pages** vs **1,670 records**

**Note:** «**Questa tabella si legge in orizzontale.** Il dataset cresce di dieci volte: PostgreSQL
passa da 610 millisecondi a quattro secondi e mezzo, Neo4j resta fermo. Il rapporto va da 390 a
2.834. Quindi il rapporto **non è una proprietà dei due sistemi, è una funzione della dimensione dei
dati.** Una misura singola avrebbe riportato un punto di questa curva e l'avrebbe chiamato "la
risposta". E a distanza 1 pareggiano: un benchmark in cui vince sempre lo stesso sistema sarebbe
sospetto.»

---

## Slide 9 — Q2 and Q4 · 1:00

**Sulla slide**
> **Q2 — Neo4j 3.5–3.7×, flat across sizes**
> Same work in both (~3M co-actor pairs); cheaper per step: pointer hop vs B-tree descent,
> hash vs sort aggregation (`COUNT(DISTINCT)`), node ids vs string keys
>
> **Q4 — tie** (1.2–2.2 ms)
> One known start node, a few hundred neighbours: nothing for either architecture to exploit

**Note:** «Q2 è un risultato di tipo diverso. Neo4j vince, ma di un **fattore costante** che non
cresce con i dati. È un aggregato globale: entrambi devono toccare tutto il grafo. Neo4j fa quasi il
doppio degli accessi di PostgreSQL e vince lo stesso, perché ogni passo costa meno. Q4 invece è un
pareggio: una traversata a due salti da un nodo noto è troppo piccola perché la profondità conti.»

Se chiedono di Q4 a ≥100 voti (Neo4j 1,9×): sotto il millisecondo si è dentro lo spread. Il segnale
vero è che PostgreSQL cresce (1,42 → 2,23 ms) e Neo4j resta piatto: Q1 in miniatura.

---

## Slide 10 — Q3: where PostgreSQL wins · 1:15 ⭐

**Sulla slide**
> **PostgreSQL 2.1–2.6×**
>
> Neo4j: one `Expand` = **78% of the work** — reads **23.6 records per film to find 2.3 genres**
> A film has ~22 relationships, all types in **one chain** (grouped by type only above 50) → walks the whole chain
>
> PostgreSQL: `Title_Genres` is its own table → **458 pages**, sequential, `Title_Principals` never opened
>
> *The same storage trade-off, seen from the other side*

**Note:** «Questa è la slide che rende credibile la 8. In Q3 vince PostgreSQL, e il piano dice
perché. In Neo4j tutte le relazioni di un film stanno in un'unica lista che mescola i tipi: per
trovare due o tre generi deve leggere anche tutti gli attori e la troupe, e scartarli. PostgreSQL ha
i generi in una tabella loro e la legge in sequenza. **È lo stesso compromesso di Q1 visto
dall'altro lato**: la catena attaccata al nodo rende il salto gratuito in Q1 e costringe a leggere
ciò che non serve in Q3.»

---

## Slide 11 — What the checks caught · 0:45

**Sulla slide**
> **Homonyms in Cypher.** `RETURN p.primaryName, count(...)` groups by *name*, merging different people
> → caught by row comparison: `Dermot Mulroney 640` vs `Akshay Kumar 661`. Fix: `WITH p, count(...)`
>
> **Missing `ANALYZE`.** `COPY` does not update planner statistics
> → Q1 distance 2: **244.3 ms → 14.7 ms** once statistics existed

**Note:** «Entrambi gli errori li hanno trovati i controlli automatici, non una rilettura del
codice. Il primo è un tranello di Cypher: la chiave di raggruppamento è implicita, e se restituisci
il nome invece del nodo raggruppi gli omonimi. Il secondo avrebbe gonfiato i tempi di PostgreSQL di
16 volte su una query.»

---

## Slide 12 — Conclusions · 1:00

**Sulla slide**
> | Query shape | Winner | Kind of advantage |
> |---|---|---|
> | Deep traversal (Q1) | Neo4j, up to 2,834× | **asymptotic** — grows with data |
> | Global aggregate (Q2) | Neo4j, 3.7× | constant |
> | Warehouse aggregation (Q3) | PostgreSQL, 2.2× | constant |
> | Local neighbourhood (Q4) | tie | none |
>
> **The choice is not graph vs relational — it is how deep and unbounded the traversal is.**
> **An honest comparison is a curve, not a ratio.**

**Note:** «Tre messaggi da portare via. Il vantaggio del grafo è asintotico **solo** sulle
traversate profonde. Sulle aggregazioni vince il relazionale. E il modo onesto di riportare un
confronto è una curva, perché il rapporto dipende dalla dimensione dei dati. Passiamo alla demo.»

---

## Demo — runbook (5:00)

**Soglia caricata: ≥1.000 voti** (rilevata da `demo.py`). Coppia Q1 a distanza 4:
*Kevin Bacon → Kacey Ainsworth*.

| Tempo | Azione | Tasti | Cosa dire |
|---:|---|---|---|
| 0:30 | Verifica dei dati | `python scripts/verify_counts.py` | «Prima di tutto: i due database contengono esattamente gli stessi dati.» |
| 0:15 | Demo già aperta e riscaldata | (in testa: `accesses ON`) | «La demo esegue le stesse query del benchmark, generate dallo stesso codice.» |
| 0:30 | Mostra le query | `4` → `t` | Cypher di 3 righe contro la CTE ricorsiva. |
| 1:30 | **Q1 distanza 4, accessi** | `b` | Secondi contro millisecondi, **2,3 milioni di pagine contro ~1.670 record**, ✓ risultati identici. |
| 1:00 | **Q3** | `6` → `b` | «E qui vince PostgreSQL»: 2.502 pagine contro 438.346 record, ✓ identici. |
| 0:45 | **Q4** | `7` → `b` | Matrix → Reloaded, Revolutions, Bound: il risultato si controlla a occhio. |
| 0:30 | Riserva | `2` → `b`, oppure Neo4j Browser | Q1 a distanza 2, per mostrare che a distanza bassa il divario è piccolo. |

**Come misura la demo.** Ogni motore esegue la query **tre volte di fila** e mostra la mediana,
dopo aver scartato le esecuzioni che partono nei primi 100 ms. Serve perché, dopo una pausa (i
13 minuti di slide), **il motore che parte per primo è rallentato per circa i suoi primi 100 ms di
lavoro**, e nella demo parte sempre PostgreSQL. Con una sola esecuzione Q3 usciva spesso vinta da
Neo4j (34 ms contro 27) e Q4 sbilanciata, al contrario del benchmark. Un'esecuzione che da sola dura
più di 100 ms non viene scartata, quindi Q1 d4 non si allunga oltre le tre esecuzioni.

**Gli accessi.** `a` si preme **dal menu principale** e resta attivo finché non lo si ripreme.
Con gli accessi attivi si aggiunge **un'esecuzione strumentata** dopo le tre cronometrate: Q1 d4 su
PostgreSQL impiega ~8 s in tutto invece di ~6, mentre Q3 e Q4 restano istantanee. Conviene
attivarli durante la preparazione e lasciarli accesi, dicendo esplicitamente che **pagine e record
sono unità diverse** e che il tempo mostrato viene dalle esecuzioni non strumentate.

**Q2 non si esegue dal vivo:** a ≥1.000 PostgreSQL impiega ~2,6 s a esecuzione (~10 s in tutto con
le tre esecuzioni e gli accessi), ed è un
risultato già coperto dalla slide 9.

### Se il prof chiede di scrivere una query

Lanciare la demo con **`python scripts/demo.py --extra-queries`**: senza nuovi file il menu è
identico. Scrivere la query in un file nuovo, per esempio `postgres/queries/q5_prof.sql` e/o
`neo4j/queries/q5_prof.cypher` (stesso nome = eseguite su entrambi e confrontate riga per riga).
Poi premere **Invio** nel menu: compare la voce `8) q5_prof`. Se la query ha un errore, la demo
lo stampa e resta aperta; si corregge il file e si rilancia la stessa voce, che rilegge il file.
Le query aggiuntive girano **in sola lettura**: un `CREATE` o un `UPDATE` viene rifiutato. Niente
parametri: i valori vanno scritti nella query. Per un confronto valido servono un `ORDER BY`
completo e le stesse colonne, altrimenti compare «RESULTS DIFFER».

### Checklist prima di entrare

- [ ] `docker compose up -d --wait`, con entrambi i container `healthy`
- [ ] `source .venv/bin/activate` dalla root del repository
- [ ] `python scripts/verify_counts.py`: *All checks passed*
- [ ] `python scripts/demo.py --extra-queries` → `w` (riscaldamento, ~9 s) → `a` (accessi ON) **prima** che inizi la presentazione, poi lasciare aperto
- [ ] Terminale con **font grande** e sfondo chiaro; finestra abbastanza larga (≥100 colonne) per le tabelle di Q4
- [ ] Chiudere Docker Desktop dashboard, browser pesanti, indicizzazione: la demo misura tempi
- [ ] **Piano B**: screenshot dell'output di Q1 d4, Q3 e Q4 in una slide nascosta alla fine del deck

### Cosa aspettarsi dai tempi della demo

È la **mediana di tre esecuzioni**, non di dieci: i numeri oscillano un po'. Riferimenti misurati
con la versione attuale di `demo.py`, PostgreSQL sempre per primo, dopo pause di 6 e 60 s:

| | PostgreSQL | Neo4j | Chi vince |
|---|---:|---:|---|
| Q1 d4 | ~1,9 s | 0,4–1,2 ms | Neo4j, sempre |
| Q3 | 10–12 ms | 22–28 ms | PostgreSQL, 12 su 12 |
| Q4 | 1,5–1,9 ms | 0,8–1,8 ms | pareggio (di solito Neo4j di poco) |

Su Q1 d4 il rapporto della demo (~2.000–4.000×) può superare il 1.051× del report: sotto i 2 ms il
tempo di Neo4j dipende da quanto il sistema è «caldo», e le tre esecuzioni di fila lo scaldano più
dell'ordine alternato del benchmark. Da dire: «il report riporta il valore prudente». Se Neo4j esce
a centinaia di millisecondi, la query è a freddo: rilanciarla. In ogni caso: «sono tre esecuzioni;
le mediane su dieci run sono nel report.»

---

## Domande probabili

Tutte con risposta pronta in **STUDIO.md §13**. Le più probabili dopo questa scaletta:

- «La BFS in SQL l'avete scritta voi?»
- «Il confronto è equo? Avete tarato i due sistemi allo stesso modo?»
- «Perché Neo4j vince Q2 se fa più accessi?»
- «Perché Neo4j perde Q3?»
- «Q4 è davvero un pareggio?»
- «Perché non avete usato GDS / pgRouting?»
- «Quanto è affidabile la misura?» → **non** dire «entro l'1%» (STUDIO.md §9)
