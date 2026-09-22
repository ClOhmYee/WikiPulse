-- Fail before changing existing identities if normalized emails collide.
DO $$ BEGIN
    IF EXISTS (SELECT lower(btrim(email)) FROM member
               GROUP BY lower(btrim(email)) HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'member email normalization collision; resolve identities before V15';
    END IF;
END $$;
CREATE UNIQUE INDEX member_normalized_email_uq ON member (lower(btrim(email)));

CREATE TABLE issue_bookmark (
    member_id BIGINT NOT NULL REFERENCES member(id) ON DELETE CASCADE,
    cluster_id BIGINT NOT NULL REFERENCES issue_cluster(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (member_id, cluster_id)
);
CREATE INDEX issue_bookmark_member_added_idx ON issue_bookmark(member_id, added_at DESC, cluster_id);
CREATE INDEX watchlist_member_added_idx ON watchlist(member_id, added_at DESC, ticker);

-- Spring Session JDBC PostgreSQL schema. Managed by db/apply_migrations.py only.
CREATE TABLE spring_session (
    primary_id CHAR(36) NOT NULL PRIMARY KEY,
    session_id CHAR(36) NOT NULL,
    creation_time BIGINT NOT NULL,
    last_access_time BIGINT NOT NULL,
    max_inactive_interval INT NOT NULL,
    expiry_time BIGINT NOT NULL,
    principal_name VARCHAR(100)
);
CREATE UNIQUE INDEX spring_session_ix1 ON spring_session(session_id);
CREATE INDEX spring_session_ix2 ON spring_session(expiry_time);
CREATE INDEX spring_session_ix3 ON spring_session(principal_name);
CREATE TABLE spring_session_attributes (
    session_primary_id CHAR(36) NOT NULL REFERENCES spring_session(primary_id) ON DELETE CASCADE,
    attribute_name VARCHAR(200) NOT NULL,
    attribute_bytes BYTEA NOT NULL,
    PRIMARY KEY (session_primary_id, attribute_name)
);
