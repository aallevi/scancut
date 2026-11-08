-- posti e categorie (aggiunti dopo: anche migrazione in db.py)

-- ------------------------------------------------------------ dove sono le cose (come l'archivio del sito)
-- Un posto e' una cosa che ne tiene altre: cassettiera, cassetto, scatola, cartella (o un'opera che ne tiene).
-- Ogni cosa e' in un posto solo, con un numero li'. I numeri sono del posto: corrono per tutto il posto
-- (posti e cose insieme), due cose nello stesso posto non hanno lo stesso numero, niente giri.
-- Le regole le tiene il database (trigger): non si controlla a mano.
CREATE TABLE place (
  id          INTEGER PRIMARY KEY,
  uuid        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  kind        TEXT NOT NULL DEFAULT 'storage' CHECK (kind IN ('storage', 'work')),
  parent_id   INTEGER REFERENCES place(id) ON DELETE RESTRICT,
  number      INTEGER CHECK (number IS NULL OR number > 0),
  archive_id  TEXT,                                 -- il record dell'archivio (Directus), quando si conosce
  notes       TEXT,
  created_at  TEXT NOT NULL,
  modified_at TEXT NOT NULL
) STRICT;
CREATE INDEX place_parent ON place(parent_id);
CREATE UNIQUE INDEX place_number ON place(COALESCE(parent_id, 0), number) WHERE number IS NOT NULL;

-- le categorie dell'archivio (Drawing, Document, …): si possono aggiungere
CREATE TABLE category (
  key      TEXT PRIMARY KEY,
  label    TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0
) STRICT;

CREATE TRIGGER place_no_loop BEFORE UPDATE OF parent_id ON place WHEN NEW.parent_id IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'a place cannot be inside itself')
  WHERE NEW.parent_id = NEW.id OR NEW.id IN (
    WITH RECURSIVE up(id) AS (SELECT NEW.parent_id UNION SELECT p.parent_id FROM place p JOIN up ON p.id = up.id WHERE p.parent_id IS NOT NULL)
    SELECT id FROM up);
END;
CREATE TRIGGER place_number_free_i BEFORE INSERT ON place WHEN NEW.number IS NOT NULL AND NEW.parent_id IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'that number is taken in this place')
  WHERE EXISTS (SELECT 1 FROM region WHERE place_id = NEW.parent_id AND place_number = NEW.number AND removed_at IS NULL);
END;
CREATE TRIGGER place_number_free_u BEFORE UPDATE OF number, parent_id ON place WHEN NEW.number IS NOT NULL AND NEW.parent_id IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'that number is taken in this place')
  WHERE EXISTS (SELECT 1 FROM region WHERE place_id = NEW.parent_id AND place_number = NEW.number AND removed_at IS NULL);
END;
CREATE TRIGGER region_place_i BEFORE INSERT ON region WHEN NEW.place_number IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'a number needs a place') WHERE NEW.place_id IS NULL;
  SELECT RAISE(ABORT, 'that number is taken in this place')
  WHERE EXISTS (SELECT 1 FROM region WHERE place_id = NEW.place_id AND place_number = NEW.place_number AND removed_at IS NULL)
     OR EXISTS (SELECT 1 FROM place WHERE parent_id = NEW.place_id AND number = NEW.place_number);
END;
CREATE TRIGGER region_place_u BEFORE UPDATE OF place_id, place_number, removed_at ON region WHEN NEW.place_number IS NOT NULL AND NEW.removed_at IS NULL
BEGIN
  SELECT RAISE(ABORT, 'a number needs a place') WHERE NEW.place_id IS NULL;
  SELECT RAISE(ABORT, 'that number is taken in this place')
  WHERE EXISTS (SELECT 1 FROM region WHERE id != NEW.id AND place_id = NEW.place_id AND place_number = NEW.place_number AND removed_at IS NULL)
     OR EXISTS (SELECT 1 FROM place WHERE parent_id = NEW.place_id AND number = NEW.place_number);
END;
CREATE TRIGGER region_category BEFORE UPDATE OF category ON region WHEN NEW.category IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'unknown category') WHERE NOT EXISTS (SELECT 1 FROM category WHERE key = NEW.category);
END;
CREATE TRIGGER item_category BEFORE UPDATE OF category ON item WHEN NEW.category IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'unknown category') WHERE NOT EXISTS (SELECT 1 FROM category WHERE key = NEW.category);
END;
CREATE TRIGGER place_keeps BEFORE DELETE ON place
BEGIN
  SELECT RAISE(ABORT, 'this place still keeps things: move them first')
  WHERE EXISTS (SELECT 1 FROM place WHERE parent_id = OLD.id) OR EXISTS (SELECT 1 FROM region WHERE place_id = OLD.id AND removed_at IS NULL)
     OR EXISTS (SELECT 1 FROM item WHERE place_id = OLD.id AND trashed_at IS NULL);
END;
