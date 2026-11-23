<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_login();
$dev = device_param();
$pdo = db();
$st = $pdo->prepare('SELECT status_json, TIMESTAMPDIFF(SECOND, last_seen, UTC_TIMESTAMP()) AS age FROM devices WHERE device_id = ?');
$st->execute([$dev]);
$d = $st->fetch();
if (!$d) json_out(['error' => 'unknown device'], 404);
$st = $pdo->prepare('SELECT * FROM readings WHERE device_id = ? ORDER BY measured_at DESC, id DESC LIMIT 1');
$st->execute([$dev]);
$r = $st->fetch();
json_out([
    'device_id' => $dev,
    'online' => $d['age'] !== null && (int)$d['age'] <= (int)cfg()['online_after_s'],
    'status' => $d['status_json'] ? json_decode($d['status_json'], true) : null,
    'reading' => $r ? cast_reading($r) : null,
]);
