# This file is managed by Ansible (files/galaxy/gxadmin/gxadmin-local.sh). Do not edit directly.
# Local gxadmin functions for the legacy pre-iRODS NFS data cleanup (VSC 2026 commitment).
# Legacy data = datasets on the old NFS disk backends (or NULL store, predating the
# distributed object store config); all new data goes to the tier1_data iRODS backend.

local_query-legacy-data-summary() { ## : Dataset count and size on legacy NFS backends by deleted/purged state
	handle_help "$@" <<-EOF
		Overview of legacy pre-iRODS data (internal_nfs_shares, new_internal_nfs_shares,
		NULL object store) grouped by deleted/purged state. Purged rows record the size
		datasets had before purging; their files should already be gone from disk.

		$ gxadmin local query-legacy-data-summary
	EOF

	read -r -d '' QUERY <<-EOF
		SELECT
			coalesce(d.object_store_id, '(null)') AS object_store,
			d.deleted,
			d.purged,
			count(*) AS datasets,
			pg_size_pretty(sum(coalesce(d.total_size, 0))::numeric) AS size
		FROM dataset d
		WHERE d.object_store_id IN ('internal_nfs_shares', 'new_internal_nfs_shares')
			OR d.object_store_id IS NULL
		GROUP BY d.object_store_id, d.deleted, d.purged
		ORDER BY d.object_store_id, d.deleted, d.purged
	EOF
}

local_query-legacy-data-per-user() { ##? <limit>: Per-user totals of non-deleted legacy NFS data, largest first
	arg_limit="${1:-50}"
	handle_help "$@" <<-EOF
		Users holding non-deleted datasets on the legacy NFS backends, with dataset
		count and total size. Drives the cleanup notification campaign. A dataset
		copied into several users' histories is counted once per user.

		$ gxadmin local query-legacy-data-per-user 20
	EOF

	read -r -d '' QUERY <<-EOF
		SELECT
			u.id AS user_id,
			u.email,
			u.active,
			count(*) AS datasets,
			sum(x.sz) AS total_bytes,
			pg_size_pretty(sum(x.sz)::numeric) AS total_size
		FROM (
			SELECT DISTINCT h.user_id, d.id, coalesce(d.total_size, 0) AS sz
			FROM dataset d
			JOIN history_dataset_association hda ON hda.dataset_id = d.id
			JOIN history h ON hda.history_id = h.id
			WHERE (d.object_store_id IN ('internal_nfs_shares', 'new_internal_nfs_shares')
				OR d.object_store_id IS NULL)
				AND NOT d.deleted
				AND h.user_id IS NOT NULL
		) x
		JOIN galaxy_user u ON u.id = x.user_id
		GROUP BY u.id, u.email, u.active
		ORDER BY sum(x.sz) DESC
		LIMIT $arg_limit
	EOF
}

local_query-legacy-data-user-datasets() { ##? <email>: Non-deleted legacy NFS datasets for one user, per history
	arg_email="$1"
	handle_help "$@" <<-EOF
		Lists a user's non-deleted datasets on the legacy NFS backends with history
		name, dataset name, size and last update. Used to build the per-user
		notification content.

		$ gxadmin local query-legacy-data-user-datasets someone@example.org
	EOF

	read -r -d '' QUERY <<-EOF
		SELECT
			h.id AS history_id,
			h.name AS history,
			hda.hid,
			hda.name AS dataset,
			pg_size_pretty(coalesce(d.total_size, 0)::numeric) AS size,
			d.object_store_id AS object_store,
			date_trunc('day', hda.update_time) AS updated
		FROM dataset d
		JOIN history_dataset_association hda ON hda.dataset_id = d.id
		JOIN history h ON hda.history_id = h.id
		JOIN galaxy_user u ON h.user_id = u.id
		WHERE u.email = '$arg_email'
			AND (d.object_store_id IN ('internal_nfs_shares', 'new_internal_nfs_shares')
				OR d.object_store_id IS NULL)
			AND NOT d.deleted
			AND NOT hda.deleted
		ORDER BY h.id, hda.hid
	EOF
}
