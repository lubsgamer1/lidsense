<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_login();
$st = db()->prepare('SELECT id, created_at, event, level, message, subject FROM alerts
                     WHERE device_id = ? ORDER BY created_at DESC, id DESC LIMIT 30');
$st->execute([device_param()]);
$rows = array_map(function ($a) { $a['created_at'] = iso($a['created_at']); return $a; }, $st->fetchAll());
json_out(['alerts' => $rows]);
