<?php
// CSV download of readings (opens in Excel). ?device=&range=24h|7d|30d|all&subject=
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_login();
$dev = device_param();
$range = $_GET['range'] ?? 'all';
$where = 'device_id = ?'; $args = [$dev];
if (isset(RANGE_HOURS[$range])) { $where .= ' AND measured_at >= UTC_TIMESTAMP(3) - INTERVAL ? HOUR'; $args[] = RANGE_HOURS[$range]; }
if (($_GET['subject'] ?? '') !== '') { $where .= ' AND subject = ?'; $args[] = $_GET['subject']; }
$pdo = db();
$pdo->setAttribute(PDO::MYSQL_ATTR_USE_BUFFERED_QUERY, false);
$st = $pdo->prepare("SELECT measured_at, device_id, seq, subject, status, quality, resonant_freq_hz, s11_db,
    return_loss_db, bandwidth_hz, q_factor, rl_spread_db, contact_rms_db, baseline_rl_db, delta_db, alert, cal_id
    FROM readings WHERE $where ORDER BY measured_at");
$st->execute($args);
$fname = preg_replace('/[^A-Za-z0-9_-]/', '', $dev) . '-readings.csv';
header('Content-Type: text/csv; charset=utf-8');
header("Content-Disposition: attachment; filename=\"$fname\"");
$out = fopen('php://output', 'w');
$first = true;
while ($r = $st->fetch()) {
    if ($first) { fputcsv($out, array_keys($r)); $first = false; }
    $r['measured_at'] = iso($r['measured_at']);
    fputcsv($out, $r);
}
