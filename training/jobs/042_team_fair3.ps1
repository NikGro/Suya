# Team fair 3: neu trainiert mit allen Naechten des Haushalts, die auf dem NAS liegen (laufend gespiegelt nach /haushalt/).
# Laedt fehlende Spenden, ordnet die Naechte aus /haushalt/frau/ der Person "joanna" zu, trainiert, vergleicht danach.
$root = "D:\SleepTraining"; $py = "$root\env\python.exe"; $share = "http://10.3.1.20:8765/haushalt"
$code = "$env:ST_BASE\code\train_e2e_team_fair.py"
& curl.exe -s -f -L -o $code "https://raw.githubusercontent.com/NikGro/Suya/main/training/train_e2e_team.py"
if (-not (Select-String -Path $code -Pattern "PROBE" -Quiet)) { Write-Output "FEHLER: alter Code geladen"; exit 1 }
& curl.exe -s -f -L -o "$env:ST_BASE\code\eval_donations.py" "https://raw.githubusercontent.com/NikGro/Suya/main/training/eval_donations.py"
$skip = @("96efe8c0")   # dieselbe Nacht wie nacht8 (schon als Aufnahme dabei)
$wife = @()
foreach ($who in "niklas", "frau") {
  $html = (& curl.exe -s -f "$share/$who/") -join "`n"
  if ($LASTEXITCODE -ne 0) { Write-Output "FEHLER: Liste $who nicht erreichbar"; exit 1 }
  foreach ($m in [regex]::Matches($html, 'href="([0-9a-f-]+\.suya)"')) {
    $f = $m.Groups[1].Value; $id = $f.Substring(0, 8)
    if ($skip -contains $id) { continue }
    if ($who -eq "frau") { $wife += "spende_$id" }
    if (-not (Test-Path "$root\data\spenden\$f")) {
      & curl.exe -s -f -o "$root\data\spenden\$f" "$share/$who/$f"
      if ($LASTEXITCODE -ne 0) { Write-Output "FEHLER: $f nicht geladen"; exit 1 }
      Write-Output "neu geladen: $who $f"
    }
  }
}
Get-ChildItem "$root\data\spenden" -Filter *.suya | ForEach-Object { Write-Output ("Spende: " + $_.Name) }
$env:MASK_SEC = "nacht7:0-3630"; $env:ITERS = "2500"; $env:W_NIGHT = "20"; $env:TEACHERS = "5"
$env:FAIR = "1"; $env:PERSONS = "joanna=joanna," + ($wife -join ",") + ";niklas=nacht,spende_"
Write-Output ("PERSONS=" + $env:PERSONS)
$env:DONATIONS = "$root\data\spenden"; $env:PROBE = "0"; $env:FINAL = "1"; $env:RUN_TAG = "_team_fair3"
& $py $code "$root\data\psg" "$root\data\home" "$env:ST_BASE\results"
# Vergleich auf den neuesten Naechten (vom neuen Modell gesehen, also geschoent; das App-Modell hat sie nicht gesehen)
$ev = "$root\data\eval_neu3"; New-Item -ItemType Directory -Force -Path $ev | Out-Null
Get-ChildItem "$root\data\spenden" -Filter *.suya | Where-Object { $_.LastWriteTime -gt (Get-Date "2026-11-14 22:00") } | Copy-Item -Destination $ev -Force
$r = "$env:ST_BASE\results"
& $py "$env:ST_BASE\code\eval_donations.py" $ev "$r\eval_team_fair3.json" "$r\model_e2e_team_fair2.pt" "$r\model_e2e_team_fair3.pt"
