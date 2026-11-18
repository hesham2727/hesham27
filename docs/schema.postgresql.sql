-- FBOSINT Analyzer 1.0.0 schema (postgresql), generated from the ORM

CREATE TABLE app_settings (
	key VARCHAR(64) NOT NULL, 
	value JSON NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (key)
);

CREATE TABLE audit_logs (
	id SERIAL NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	user_id INTEGER, 
	username VARCHAR(64) NOT NULL, 
	action VARCHAR(64) NOT NULL, 
	target_type VARCHAR(32) NOT NULL, 
	target_id VARCHAR(64) NOT NULL, 
	ip_address VARCHAR(64) NOT NULL, 
	success BOOLEAN NOT NULL, 
	details JSON NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE INDEX ix_audit_logs_action ON audit_logs (action);

CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id);

CREATE TABLE schema_version (
	id SERIAL NOT NULL, 
	version INTEGER NOT NULL, 
	applied_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	full_name VARCHAR(128) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	language VARCHAR(5) NOT NULL, 
	failed_logins INTEGER NOT NULL, 
	locked_until TIMESTAMP WITH TIME ZONE, 
	last_login_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE encrypted_credentials (
	id SERIAL NOT NULL, 
	name VARCHAR(64) NOT NULL, 
	owner_user_id INTEGER, 
	ciphertext TEXT NOT NULL, 
	meta JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_cred_owner UNIQUE (name, owner_user_id), 
	FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE investigations (
	id SERIAL NOT NULL, 
	reference VARCHAR(32) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	target_input VARCHAR(500) NOT NULL, 
	target_type VARCHAR(32) NOT NULL, 
	normalized_url VARCHAR(500) NOT NULL, 
	identifier VARCHAR(200) NOT NULL, 
	object_type VARCHAR(32) NOT NULL, 
	graph_object_id VARCHAR(64) NOT NULL, 
	purpose TEXT NOT NULL, 
	legal_basis VARCHAR(200) NOT NULL, 
	notes TEXT NOT NULL, 
	options JSON NOT NULL, 
	extra_urls JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	status_message TEXT NOT NULL, 
	limitations JSON NOT NULL, 
	created_by_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	completed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_investigations_status ON investigations (status);

CREATE INDEX ix_investigations_created_at ON investigations (created_at);

CREATE UNIQUE INDEX ix_investigations_reference ON investigations (reference);

CREATE TABLE oauth_states (
	id SERIAL NOT NULL, 
	state_hash VARCHAR(64) NOT NULL, 
	user_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	used BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (state_hash), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE sessions (
	id SERIAL NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	csrf_token VARCHAR(64) NOT NULL, 
	user_id INTEGER NOT NULL, 
	client VARCHAR(20) NOT NULL, 
	ip_address VARCHAR(64) NOT NULL, 
	user_agent VARCHAR(255) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	revoked BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_sessions_token_hash ON sessions (token_hash);

CREATE INDEX ix_sessions_user_id ON sessions (user_id);

CREATE TABLE collection_events (
	id SERIAL NOT NULL, 
	investigation_id INTEGER NOT NULL, 
	step VARCHAR(64) NOT NULL, 
	level VARCHAR(10) NOT NULL, 
	message TEXT NOT NULL, 
	details JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(investigation_id) REFERENCES investigations (id) ON DELETE CASCADE
);

CREATE INDEX ix_collection_events_investigation_id ON collection_events (investigation_id);

CREATE TABLE data_points (
	id SERIAL NOT NULL, 
	investigation_id INTEGER NOT NULL, 
	category VARCHAR(32) NOT NULL, 
	field VARCHAR(64) NOT NULL, 
	value TEXT NOT NULL, 
	normalized_value TEXT NOT NULL, 
	source_url VARCHAR(1000) NOT NULL, 
	source_type VARCHAR(32) NOT NULL, 
	extraction_method VARCHAR(32) NOT NULL, 
	collected_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	availability VARCHAR(20) NOT NULL, 
	verification_status VARCHAR(20) NOT NULL, 
	confidence VARCHAR(10) NOT NULL, 
	classification VARCHAR(32) NOT NULL, 
	manually_reviewed BOOLEAN NOT NULL, 
	notes TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(investigation_id) REFERENCES investigations (id) ON DELETE CASCADE
);

CREATE INDEX ix_dp_inv_cat ON data_points (investigation_id, category);

CREATE INDEX ix_data_points_investigation_id ON data_points (investigation_id);

CREATE TABLE media_items (
	id SERIAL NOT NULL, 
	investigation_id INTEGER NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	source_url VARCHAR(2000) NOT NULL, 
	source_type VARCHAR(32) NOT NULL, 
	external_id VARCHAR(128) NOT NULL, 
	caption TEXT NOT NULL, 
	created_time TIMESTAMP WITH TIME ZONE, 
	local_path VARCHAR(500) NOT NULL, 
	mime_type VARCHAR(64) NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	width INTEGER NOT NULL, 
	height INTEGER NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	phash VARCHAR(16) NOT NULL, 
	dhash VARCHAR(16) NOT NULL, 
	metadata_json JSON NOT NULL, 
	duplicate_group INTEGER, 
	status VARCHAR(20) NOT NULL, 
	error_message TEXT NOT NULL, 
	collected_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(investigation_id) REFERENCES investigations (id) ON DELETE CASCADE
);

CREATE INDEX ix_media_items_sha256 ON media_items (sha256);

CREATE INDEX ix_media_items_investigation_id ON media_items (investigation_id);

CREATE TABLE posts (
	id SERIAL NOT NULL, 
	investigation_id INTEGER NOT NULL, 
	external_id VARCHAR(128) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	parent_external_id VARCHAR(128) NOT NULL, 
	message TEXT NOT NULL, 
	created_time TIMESTAMP WITH TIME ZONE, 
	permalink VARCHAR(1000) NOT NULL, 
	shared_link VARCHAR(1000) NOT NULL, 
	source_url VARCHAR(1000) NOT NULL, 
	source_type VARCHAR(32) NOT NULL, 
	collected_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_post_ext UNIQUE (investigation_id, external_id, kind), 
	FOREIGN KEY(investigation_id) REFERENCES investigations (id) ON DELETE CASCADE
);

CREATE INDEX ix_posts_investigation_id ON posts (investigation_id);

CREATE INDEX ix_posts_created_time ON posts (created_time);

CREATE TABLE report_exports (
	id SERIAL NOT NULL, 
	investigation_id INTEGER NOT NULL, 
	format VARCHAR(8) NOT NULL, 
	language VARCHAR(5) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	created_by_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(investigation_id) REFERENCES investigations (id) ON DELETE CASCADE
);

CREATE INDEX ix_report_exports_investigation_id ON report_exports (investigation_id);

CREATE TABLE sources (
	id SERIAL NOT NULL, 
	investigation_id INTEGER NOT NULL, 
	url VARCHAR(2000) NOT NULL, 
	final_url VARCHAR(2000) NOT NULL, 
	domain VARCHAR(255) NOT NULL, 
	source_type VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	http_status INTEGER, 
	title VARCHAR(500) NOT NULL, 
	content_sha256 VARCHAR(64) NOT NULL, 
	error_message TEXT NOT NULL, 
	fetched_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(investigation_id) REFERENCES investigations (id) ON DELETE CASCADE
);

CREATE INDEX ix_sources_investigation_id ON sources (investigation_id);
