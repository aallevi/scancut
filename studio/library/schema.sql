-- Scan Studio library (catalogo): uno per libreria, dentro il pacchetto <nome>.scanlib/library.sqlite
-- SQLite: formato raccomandato dalla Library of Congress per i dati. Tabelle STRICT, chiavi esterne,
-- UUID per tutto cio' che si puo' unire fra librerie. I pixel non stanno qui: solo file su disco.
-- Coordinate: pixel dell'asset a piena risoluzione, origine in alto a sinistra.
-- Date: ISO 8601; le date incerte degli oggetti in EDTF (es. "2014-05?", "199X").

PRAGMA foreign_keys = ON;

CREATE TABLE meta (                      -- versione dello schema, uuid e nome della libreria
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
) STRICT;

-- ------------------------------------------------------------ file (i pixel veri, mai modificati)
CREATE TABLE asset (
  id            INTEGER PRIMARY KEY,
  uuid          TEXT NOT NULL UNIQUE,
  sha256        TEXT NOT NULL,                      -- fissita': il file e' sempre questo
  size          INTEGER NOT NULL,
  storage       TEXT NOT NULL CHECK (storage IN ('managed', 'referenced')),
  path          TEXT NOT NULL,                      -- managed: relativo al pacchetto (store/ab/abcd….tif); referenced: assoluto
  original_name TEXT NOT NULL,
  mime          TEXT,
  width         INTEGER,
  height        INTEGER,
  dpi           REAL,
  bits          INTEGER,                            -- per canale: 8 o 16
  channels      INTEGER,
  icc           TEXT,                               -- descrizione del profilo colore
  file_mtime    TEXT,
  imported_at   TEXT NOT NULL,
  derived_from  INTEGER REFERENCES asset(id) ON DELETE SET NULL,   -- copia ritoccata (es. in Affinity): da quale file
  made_with     TEXT,                               -- l'app che l'ha fatta ("Affinity"), o NULL per un originale
  technical     TEXT CHECK (technical IS NULL OR json_valid(technical))   -- EXIF/XMP letti all'import
) STRICT;
CREATE INDEX asset_sha ON asset(sha256);
CREATE INDEX asset_derived ON asset(derived_from);

-- ------------------------------------------------------------ serie (quaderni, raccolte di scansioni)
-- Una serie e' una cosa: nome, note. Gli oggetti la indicano; le cartelle sono una sua vista.
CREATE TABLE series (
  id         INTEGER PRIMARY KEY,
  uuid       TEXT NOT NULL UNIQUE,
  name       TEXT NOT NULL UNIQUE COLLATE NOCASE,
  notes      TEXT,
  created_at TEXT NOT NULL
) STRICT;

-- ------------------------------------------------------------ oggetti dell'archivio
-- Un item e' la cosa che si archivia: una scansione, una foto, un quaderno, un documento.
CREATE TABLE item (
  id          INTEGER PRIMARY KEY,
  uuid        TEXT NOT NULL UNIQUE,
  kind        TEXT NOT NULL DEFAULT 'scan',         -- scan | photo | document | object | ...
  parent_id   INTEGER REFERENCES item(id) ON DELETE CASCADE,   -- parti: un quaderno e le sue pagine, un oggetto e i suoi pezzi
  title       TEXT,
  date        TEXT,                                 -- EDTF: quando e' stato fatto l'oggetto
  series_id   INTEGER REFERENCES series(id) ON DELETE SET NULL,   -- la serie (NULL: in nessuna)
  notes       TEXT,
  created_at  TEXT NOT NULL,
  modified_at TEXT NOT NULL,
  trashed_at  TEXT                                  -- nel cestino della libreria (mai cancellato subito)
) STRICT;
CREATE INDEX item_date ON item(trashed_at, date, created_at);
CREATE INDEX item_series ON item(series_id);
CREATE INDEX item_parent ON item(parent_id);

CREATE TABLE item_asset (                -- pagine: fronte, retro, dettagli, piu' scansioni dello stesso oggetto
  item_id  INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
  asset_id INTEGER NOT NULL REFERENCES asset(id) ON DELETE RESTRICT,
  role     TEXT NOT NULL DEFAULT 'view',            -- view | front | back | detail | edit (copia ritoccata)
  position INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (item_id, asset_id)
) STRICT;
CREATE INDEX item_asset_asset ON item_asset(asset_id);

-- ------------------------------------------------------------ zone: fogli, aree di testo, figure
-- Una zona e' una selezione su un asset: il foglio ritagliato, un'area di scrittura, una figura.
-- Le zone si annidano (foglio -> aree di testo dentro). Geometria e ritocchi come nello studio di oggi.
CREATE TABLE region (
  id          INTEGER PRIMARY KEY,
  uuid        TEXT NOT NULL UNIQUE,
  item_id     INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
  asset_id    INTEGER NOT NULL REFERENCES asset(id) ON DELETE RESTRICT,
  parent_id   INTEGER REFERENCES region(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL,                        -- sheet | text | figure | box
  label       TEXT,
  geometry    TEXT NOT NULL CHECK (json_valid(geometry)),   -- {"poly":[[x,y],…]} o {"box":[x0,y0,x1,y1]}
  source      TEXT CHECK (source IS NULL OR json_valid(source)),  -- motore, parametri, maschera in cache
  ops         TEXT CHECK (ops IS NULL OR json_valid(ops)),        -- ritocchi in ordine (aggiungi, togli, inverti…)
  rotation    INTEGER NOT NULL DEFAULT 0,           -- gradi a passi di 90, all'export
  export_on   INTEGER NOT NULL DEFAULT 1,
  position    INTEGER NOT NULL DEFAULT 0,           -- ordine di lettura
  color       TEXT,                                 -- il colore della selezione (vista testo, export)
  created_at  TEXT NOT NULL,
  modified_at TEXT NOT NULL
) STRICT;
CREATE INDEX region_item ON region(item_id, position);
CREATE INDEX region_parent ON region(parent_id);

-- ------------------------------------------------------------ testo: letture e correzioni
-- Ogni lettura OCR resta (versioni): motore, modello, tutto cio' che ha dato. Le correzioni a mano
-- sono uno strato sopra, con le loro versioni; il testo "attuale" e' l'ultima correzione o l'ultima lettura.
CREATE TABLE reading (
  id          INTEGER PRIMARY KEY,
  uuid        TEXT NOT NULL UNIQUE,
  region_id   INTEGER REFERENCES region(id) ON DELETE CASCADE,
  asset_id    INTEGER NOT NULL REFERENCES asset(id) ON DELETE RESTRICT,   -- lettura dell'asset intero se region_id e' NULL
  engine      TEXT NOT NULL,                        -- vision | ollama | …
  model       TEXT,                                 -- glm-ocr, qwen3-vl:8b, …
  model_digest TEXT,                                -- versione esatta del modello
  params      TEXT CHECK (params IS NULL OR json_valid(params)),
  languages   TEXT,                                 -- es. "it,en"
  confidence  REAL,
  plain       TEXT NOT NULL DEFAULT '',             -- testo semplice (ricerca)
  doc         TEXT CHECK (doc IS NULL OR json_valid(doc)),   -- documento strutturato (blocchi, righe, parole, riquadri, lingue, stili, figure)
  raw         TEXT,                                 -- uscita grezza del motore, cosi' com'e'
  created_at  TEXT NOT NULL
) STRICT;
CREATE INDEX reading_region ON reading(region_id, created_at);
CREATE INDEX reading_asset ON reading(asset_id, created_at);

CREATE TABLE correction (
  id          INTEGER PRIMARY KEY,
  reading_id  INTEGER NOT NULL REFERENCES reading(id) ON DELETE CASCADE,
  version     INTEGER NOT NULL,
  plain       TEXT NOT NULL,
  doc         TEXT CHECK (doc IS NULL OR json_valid(doc)),
  note        TEXT,
  created_at  TEXT NOT NULL,
  UNIQUE (reading_id, version)
) STRICT;

-- un testo indica anche i file che lo mostrano: il ritaglio della sua zona, una copia ritoccata.
-- (la zona della scansione e' reading.region_id; qui i file, per andare dal ritaglio al suo testo)
CREATE TABLE text_link (
  reading_id INTEGER NOT NULL REFERENCES reading(id) ON DELETE CASCADE,
  asset_id   INTEGER NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
  PRIMARY KEY (reading_id, asset_id)
) STRICT;
CREATE INDEX text_link_asset ON text_link(asset_id);

-- il testo attuale di ogni lettura: l'ultima correzione, o la lettura com'e'
CREATE VIEW current_text AS
SELECT r.id AS reading_id, r.uuid, r.region_id, r.asset_id, r.engine, r.model, r.created_at,
       COALESCE(c.plain, r.plain) AS plain, COALESCE(c.doc, r.doc) AS doc, c.version AS corrected_version
FROM reading r
LEFT JOIN correction c ON c.reading_id = r.id
  AND c.version = (SELECT MAX(version) FROM correction WHERE reading_id = r.id);

-- ------------------------------------------------------------ ordinare: etichette e raccolte
CREATE TABLE tag (
  id    INTEGER PRIMARY KEY,
  name  TEXT NOT NULL UNIQUE COLLATE NOCASE,
  color TEXT
) STRICT;
CREATE TABLE item_tag (
  item_id INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
  tag_id  INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
  PRIMARY KEY (item_id, tag_id)
) STRICT;
CREATE INDEX item_tag_tag ON item_tag(tag_id);

CREATE TABLE collection (                -- una lista a mano, o una ricerca salvata (query)
  id         INTEGER PRIMARY KEY,
  uuid       TEXT NOT NULL UNIQUE,
  name       TEXT NOT NULL,
  parent_id  INTEGER REFERENCES collection(id) ON DELETE CASCADE,
  query      TEXT CHECK (query IS NULL OR json_valid(query)),
  position   INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
) STRICT;
CREATE TABLE collection_item (
  collection_id INTEGER NOT NULL REFERENCES collection(id) ON DELETE CASCADE,
  item_id       INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
  position      INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (collection_id, item_id)
) STRICT;

-- ------------------------------------------------------------ tagli e altre rappresentazioni
-- Ogni file fatto dalla libreria: il ritaglio (cut) di una zona, PDF ricercabile, LaTeX, … Con checksum e
-- impostazioni. Un taglio segue la sua zona: cambia la zona, si rifa' (il file di prima resta nella storia).
CREATE TABLE cut (
  id          INTEGER PRIMARY KEY,
  uuid        TEXT NOT NULL UNIQUE,
  item_id     INTEGER REFERENCES item(id) ON DELETE SET NULL,
  region_id   INTEGER REFERENCES region(id) ON DELETE SET NULL,
  format      TEXT NOT NULL,                        -- png | jxl | pdf | tex | md | docx | json
  path        TEXT NOT NULL,
  sha256      TEXT,
  settings    TEXT CHECK (settings IS NULL OR json_valid(settings)),
  source_versions TEXT CHECK (source_versions IS NULL OR json_valid(source_versions)),  -- quali letture/correzioni
  created_at  TEXT NOT NULL
) STRICT;
CREATE INDEX cut_item ON cut(item_id);
CREATE INDEX cut_region ON cut(region_id);
CREATE INDEX cut_path ON cut(path);

-- ------------------------------------------------------------ conservazione (come PREMIS)
CREATE TABLE event (                     -- registro di tutto cio' che succede: import, letture, ritocchi, export, controlli
  id          INTEGER PRIMARY KEY,
  at          TEXT NOT NULL,
  type        TEXT NOT NULL,                        -- import | fixity | edit | read | correct | cut | recut | rotate | merge | migrate
  entity      TEXT NOT NULL,                        -- asset | item | region | reading | library
  entity_uuid TEXT,
  outcome     TEXT NOT NULL DEFAULT 'ok',           -- ok | fail | warning
  detail      TEXT CHECK (detail IS NULL OR json_valid(detail)),
  agent       TEXT                                  -- "Scan Studio 0.9", motore, utente
) STRICT;
CREATE INDEX event_entity ON event(entity_uuid, at);
CREATE INDEX event_type ON event(type, at);

-- ------------------------------------------------------------ vettori (ricerca per somiglianza)
CREATE TABLE embedding (
  id         INTEGER PRIMARY KEY,
  owner      TEXT NOT NULL,                         -- asset | region | reading
  owner_id   INTEGER NOT NULL,
  model      TEXT NOT NULL,                         -- siglip2, embeddinggemma, …
  dim        INTEGER NOT NULL,
  vector     BLOB NOT NULL,                         -- float32, dim * 4 byte
  created_at TEXT NOT NULL,
  UNIQUE (owner, owner_id, model)
) STRICT;

-- ------------------------------------------------------------ impostazioni della libreria
CREATE TABLE setting (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL CHECK (json_valid(value))
) STRICT;

-- ------------------------------------------------------------ ricerca a tutto testo (FTS5)
-- titolo, note, etichette delle zone e testo attuale, per item: tenuta aggiornata da db.py
CREATE VIRTUAL TABLE search USING fts5(
  item_uuid UNINDEXED, title, notes, labels, text,
  tokenize = 'unicode61 remove_diacritics 2'
);
