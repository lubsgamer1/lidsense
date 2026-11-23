<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_login();
$st = db()->prepare('SELECT measured_at, start_hz, stop_hz, points, s11_db_json FROM sweeps
                     WHERE device_id = ? ORDER BY measured_at DESC LIMIT 1');
$st->execute([device_param()]);
$s = $st->fetch();
json_out(['sweep' => $s ? [
    'measured_at' => iso($s['measured_at']), 'start_hz' => (float)$s['start_hz'], 'stop_hz' => (float)$s['stop_hz'],
    'points' => (int)$s['points'], 's11_db' => json_decode($s['s11_db_json'], true),
] : null]);
