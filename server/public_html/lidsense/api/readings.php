<?php
// Readings for the trend chart. Up to 24 h: every reading. Longer ranges: averaged buckets of
// good readings (5 min for 7 days, 30 min for 30 days) so the browser stays fast.
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_login();
$dev = device_param();
$range = $_GET['range'] ?? '6h';
$hours = RANGE_HOURS[$range] ?? 6;
$subject = $_GET['subject'] ?? '';
$where = 'device_id = ? AND measured_at >= UTC_TIMESTAMP(3) - INTERVAL ? HOUR';
$args = [$dev, $hours];
if ($subject !== '') { $where .= ' AND subject = ?'; $args[] = $subject; }

if ($hours <= 24) {
    $st = db()->prepare("SELECT id, seq, measured_at, subject, status, quality, resonant_freq_hz, s11_db,
        return_loss_db, bandwidth_hz, q_factor, rl_spread_db, contact_rms_db, baseline_rl_db, delta_db, alert
        FROM readings WHERE $where ORDER BY measured_at LIMIT 20000");
    $st->execute($args);
    $rows = array_map('cast_reading', $st->fetchAll());
    json_out(['readings' => $rows, 'bucket_s' => 0]);
}
$bucket = $hours <= 168 ? 300 : 1800;
$st = db()->prepare("SELECT FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(measured_at) / $bucket) * $bucket) AS measured_at,
        AVG(resonant_freq_hz) AS resonant_freq_hz, AVG(s11_db) AS s11_db, AVG(return_loss_db) AS return_loss_db,
        AVG(delta_db) AS delta_db, COUNT(*) AS n, 'good' AS quality
    FROM readings WHERE $where AND quality = 'good' GROUP BY 1 ORDER BY 1");
$st->execute($args);
$rows = array_map(function ($r) { $r['measured_at'] .= '.000'; return cast_reading($r); }, $st->fetchAll());
json_out(['readings' => $rows, 'bucket_s' => $bucket]);
