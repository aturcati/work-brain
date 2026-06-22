// work-brain Kuzu schema
// Generated from CLAUDE.md closed vocabulary.
// Rebuilt by /kb-graph project — do not edit by hand.
// Last generated: 2026-05-11

// ─── Node tables ─────────────────────────────────────────────

CREATE NODE TABLE Person (
  slug STRING,
  aliases STRING[],
  status STRING,
  tags STRING[],
  confidence STRING,
  created STRING,
  modified STRING,
  last_verified STRING,
  PRIMARY KEY (slug)
);

CREATE NODE TABLE Org (
  slug STRING,
  aliases STRING[],
  status STRING,
  tags STRING[],
  confidence STRING,
  created STRING,
  modified STRING,
  last_verified STRING,
  PRIMARY KEY (slug)
);

CREATE NODE TABLE Project (
  slug STRING,
  aliases STRING[],
  status STRING,
  tags STRING[],
  confidence STRING,
  created STRING,
  modified STRING,
  last_verified STRING,
  PRIMARY KEY (slug)
);

CREATE NODE TABLE Topic (
  slug STRING,
  aliases STRING[],
  status STRING,
  tags STRING[],
  confidence STRING,
  created STRING,
  modified STRING,
  last_verified STRING,
  PRIMARY KEY (slug)
);

CREATE NODE TABLE Decision (
  slug STRING,
  status STRING,
  tags STRING[],
  confidence STRING,
  created STRING,
  modified STRING,
  last_verified STRING,
  PRIMARY KEY (slug)
);

CREATE NODE TABLE Meeting (
  slug STRING,
  date STRING,
  status STRING,
  tags STRING[],
  confidence STRING,
  created STRING,
  modified STRING,
  PRIMARY KEY (slug)
);

CREATE NODE TABLE Source (
  slug STRING,
  path STRING,
  channel STRING,
  captured_at STRING,
  provider STRING,
  PRIMARY KEY (slug)
);

CREATE NODE TABLE Artifact (
  slug STRING,
  aliases STRING[],
  status STRING,
  created STRING,
  modified STRING,
  PRIMARY KEY (slug)
);

CREATE NODE TABLE Event (
  slug STRING,
  date STRING,
  status STRING,
  created STRING,
  modified STRING,
  PRIMARY KEY (slug)
);

// ─── Structural edge tables ───────────────────────────────────

CREATE REL TABLE part_of (
  FROM Project TO Project,
  FROM Topic TO Topic,
  FROM Org TO Org
);

CREATE REL TABLE instance_of (
  FROM Person TO Topic,
  FROM Artifact TO Topic,
  FROM Event TO Topic
);

CREATE REL TABLE related (
  FROM Person TO Topic,
  FROM Project TO Topic,
  FROM Topic TO Topic,
  FROM Org TO Topic,
  FROM Decision TO Topic,
  FROM Meeting TO Topic,
  FROM Artifact TO Topic,
  FROM Event TO Topic
);

// ─── Agentic edge tables ──────────────────────────────────────

CREATE REL TABLE works_at (FROM Person TO Org);
CREATE REL TABLE attended (
  FROM Person TO Meeting,
  FROM Meeting TO Person
);

CREATE REL TABLE authored (
  FROM Person TO Artifact,
  FROM Person TO Source,
  FROM Person TO Topic
);

CREATE REL TABLE owns (
  FROM Person TO Project,
  FROM Org TO Project
);

CREATE REL TABLE reports_to (FROM Person TO Person);

// ─── Epistemic edge tables ────────────────────────────────────

CREATE REL TABLE sources (
  FROM Topic TO Source,
  FROM Decision TO Source,
  FROM Meeting TO Source,
  FROM Project TO Source,
  FROM Person TO Source,
  FROM Artifact TO Source,
  FROM Event TO Source
);

CREATE REL TABLE derived_from (
  FROM Topic TO Source,
  FROM Decision TO Source,
  FROM Artifact TO Source
);

CREATE REL TABLE cites (
  FROM Topic TO Source,
  FROM Decision TO Source,
  FROM Artifact TO Source
);

CREATE REL TABLE supersedes (
  FROM Decision TO Decision,
  FROM Topic TO Topic,
  FROM Artifact TO Artifact
);

CREATE REL TABLE superseded_by (
  FROM Decision TO Decision,
  FROM Topic TO Topic,
  FROM Artifact TO Artifact
);

CREATE REL TABLE contradicts (
  FROM Topic TO Topic,
  FROM Decision TO Decision
);

CREATE REL TABLE confirms (
  FROM Topic TO Topic,
  FROM Decision TO Decision
);

// ─── Causal edge tables ───────────────────────────────────────

CREATE REL TABLE depends_on (
  FROM Project TO Project,
  FROM Decision TO Decision,
  FROM Event TO Event
);

CREATE REL TABLE caused_by (
  FROM Event TO Event,
  FROM Decision TO Event,
  FROM Project TO Decision
);

CREATE REL TABLE decided (FROM Meeting TO Decision);

CREATE REL TABLE mentions (
  FROM Meeting TO Person,
  FROM Meeting TO Project,
  FROM Meeting TO Topic,
  FROM Meeting TO Org,
  FROM Topic TO Person,
  FROM Topic TO Project,
  FROM Topic TO Org,
  FROM Source TO Person,
  FROM Source TO Project,
  FROM Source TO Topic
);
