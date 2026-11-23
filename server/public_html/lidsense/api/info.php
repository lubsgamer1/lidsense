<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
$user = require_login();
$c = cfg();
$rows = db()->query('SELECT device_id, name, last_seen, TIMESTAMPDIFF(SECOND, last_seen, UTC_TIMESTAMP()) AS age
                     FROM devices ORDER BY name, device_id')->fetchAll();
$devices = array_map(fn($r) => [
    'device_id' => $r['device_id'], 'name' => $r['name'] ?: $r['device_id'],
    'last_seen' => iso($r['last_seen']),
    'online' => $r['age'] !== null && (int)$r['age'] <= (int)$c['online_after_s'],
], $rows);
json_out(['source' => 'cloud', 'controls' => false, 'user' => $user, 'now' => gmdate('c'),
          'devices' => $devices, 'bands' => $c['bands'], 'alert_delta_db' => $c['alert_delta_db']]);
