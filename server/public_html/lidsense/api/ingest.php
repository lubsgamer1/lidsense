<?php
// POST from the Raspberry Pi: {device_id, status, messages:[{id, kind, data}]}
// Header X-Device-Key: <device API key>. Responds {accepted:[ids]} so the Pi can clear its outbox.
// Safe to retry: duplicates are ignored via UNIQUE keys (device_id + seq / local_id).
declare(strict_types=1);
require __DIR__ . '/lib.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') json_out(['error' => 'POST only'], 405);
$body = json_decode(file_get_contents('php://input') ?: '', true);
if (!is_array($body) || !isset($body['device_id'])) json_out(['error' => 'bad JSON'], 400);

$deviceId = str_or($body['device_id']);
$key = $_SERVER['HTTP_X_DEVICE_KEY'] ?? '';
$pdo = db();
$st = $pdo->prepare('SELECT api_key_hash FROM devices WHERE device_id = ?');
$st->execute([$deviceId]);
$hash = $st->fetchColumn();
if (!$hash || !hash_equals((string)$hash, hash('sha256', $key))) {
    json_out(['error' => 'unknown device or wrong key'], 403);
}

$insReading = $pdo->prepare('INSERT IGNORE INTO readings
  (device_id, seq, measured_at, subject, status, quality, resonant_freq_hz, s11_db, return_loss_db,
   bandwidth_hz, q_factor, rl_spread_db, contact_rms_db, baseline_rl_db, delta_db, alert, cal_id)
  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)');
$findReading = $pdo->prepare('SELECT id FROM readings WHERE device_id = ? AND seq = ?');
$insSweep = $pdo->prepare('INSERT IGNORE INTO sweeps
  (reading_id, device_id, measured_at, start_hz, stop_hz, points, s11_db_json) VALUES (?,?,?,?,?,?,?)');
$insAlert = $pdo->prepare('INSERT IGNORE INTO alerts
  (device_id, local_id, created_at, event, level, message, subject) VALUES (?,?,?,?,?,?,?)');
$insBase = $pdo->prepare('INSERT IGNORE INTO baselines
  (device_id, subject, created_at, return_loss_db, resonant_freq_hz, sd_db, n) VALUES (?,?,?,?,?,?,?)');

$accepted = [];
$pdo->beginTransaction();
try {
    foreach (($body['messages'] ?? []) as $m) {
        $id = $m['id'] ?? null; $d = $m['data'] ?? null;
        if (!is_int($id) || !is_array($d)) continue;
        switch ($m['kind'] ?? '') {
            case 'reading':
                $t = to_mysql_time($d['measured_at'] ?? null);
                if (!$t || !isset($d['seq'])) break;
                $insReading->execute([$deviceId, (int)$d['seq'], $t, str_or($d['subject'] ?? '', '', 32),
                    isset($d['status']) ? str_or($d['status'], '', 32) : null, str_or($d['quality'] ?? 'good', 'good', 16),
                    num_or_null($d['resonant_freq_hz'] ?? null), num_or_null($d['s11_db'] ?? null),
                    num_or_null($d['return_loss_db'] ?? null), num_or_null($d['bandwidth_hz'] ?? null),
                    num_or_null($d['q_factor'] ?? null), num_or_null($d['rl_spread_db'] ?? null),
                    num_or_null($d['contact_rms_db'] ?? null), num_or_null($d['baseline_rl_db'] ?? null),
                    num_or_null($d['delta_db'] ?? null), isset($d['alert']) ? str_or($d['alert'], '', 32) : null,
                    isset($d['cal_id']) ? str_or($d['cal_id']) : null]);
                if (isset($d['sweep']['s11_db']) && is_array($d['sweep']['s11_db'])) {
                    $findReading->execute([$deviceId, (int)$d['seq']]);
                    $rid = $findReading->fetchColumn();
                    $vals = array_map('floatval', array_slice($d['sweep']['s11_db'], 0, 2048));
                    if ($rid) $insSweep->execute([$rid, $deviceId, $t, (float)$d['sweep']['start_hz'],
                        (float)$d['sweep']['stop_hz'], count($vals), json_encode($vals)]);
                }
                break;
            case 'alert':
                $insAlert->execute([$deviceId, (int)($d['id'] ?? $id), to_mysql_time($d['created_at'] ?? null) ?? gmdate('Y-m-d H:i:s'),
                    str_or($d['event'] ?? 'info', 'info', 16), isset($d['level']) ? str_or($d['level'], '', 32) : null,
                    str_or($d['message'] ?? '', '', 500), str_or($d['subject'] ?? '', '', 32)]);
                break;
            case 'baseline':
                $insBase->execute([$deviceId, str_or($d['subject'] ?? '', '', 32),
                    to_mysql_time($d['created_at'] ?? null) ?? gmdate('Y-m-d H:i:s'),
                    (float)($d['return_loss_db'] ?? 0), (float)($d['resonant_freq_hz'] ?? 0),
                    (float)($d['sd_db'] ?? 0), (int)($d['n'] ?? 0)]);
                break;
            default:
                // unknown kinds are acknowledged so they don't block the queue
        }
        $accepted[] = $id;
    }
    $pdo->prepare('UPDATE devices SET last_seen = UTC_TIMESTAMP(3), status_json = ? WHERE device_id = ?')
        ->execute([json_encode($body['status'] ?? null), $deviceId]);
    $pdo->commit();
} catch (Throwable $e) {
    $pdo->rollBack();
    error_log('lidsense ingest: ' . $e->getMessage());
    json_out(['error' => 'database error'], 500);
}
json_out(['accepted' => $accepted]);
