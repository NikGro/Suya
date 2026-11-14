"""Vergleicht fertige Modelle auf gespendeten Nächten, die keins von ihnen beim Training gesehen hat.

Aufruf: python eval_donations.py <Ordner mit .suya> <Ausgabe.json> <modell1.pt> [<modell2.pt> …]

Normierung genau wie die App (LogMel.normalize): Bilder mit eigenen Klängen durch den Band-Median der übrigen
ersetzen, je Band den Median abziehen, durch die Streuung aller zentrierten Werte teilen. Epochen mit Klängen
oder ohne Watch-Phase zählen nicht. Maß: Cohens Kappa und Anteil gleicher Epochen gegen die Watch.
"""
import glob, json, os, struct, sys, zlib
import numpy as np, torch, torch.nn as nn

dev = "cuda" if torch.cuda.is_available() else "cpu"
NAMES = ["Wach", "REM", "Kern", "Tief"]


class Net(nn.Module):
    def __init__(s, h=96):
        super().__init__()
        s.cnn = nn.Sequential(
            nn.Conv2d(1, 16, 5, padding=2), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d((2, 2)),
            nn.Conv2d(16, 32, 5, padding=2), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d((2, 3)),
            nn.Conv2d(32, 64, (3, 5), padding=(1, 2)), nn.BatchNorm2d(64), nn.ReLU(), nn.MaxPool2d((2, 5)),
            nn.Conv2d(64, h, 3, padding=1), nn.BatchNorm2d(h), nn.ReLU(), nn.AdaptiveAvgPool2d(1))
        s.drop = nn.Dropout(0.3)
        s.gru = nn.GRU(h, h, num_layers=2, batch_first=True, bidirectional=True, dropout=0.2)
        s.out = nn.Linear(2 * h, 4)


def norm_frames(M, masked):
    if masked:
        keep = torch.ones(M.shape[1], dtype=torch.bool)
        for a, b in masked:
            keep[max(0, int(a)): max(0, int(b))] = False
        if keep.sum() > M.shape[1] // 4:
            M = M.clone()
            M[:, ~keep] = M[:, keep].median(1, keepdim=True).values
    M = M - M.median(1, keepdim=True).values
    return M / (M.std() + 1e-6)


def load(path):
    raw = zlib.decompress(open(path, "rb").read(), -15)
    assert raw[:4] == b"SUYA" and raw[4] == 1, path
    n = struct.unpack("<I", raw[5:9])[0]
    head = json.loads(raw[9:9 + n])
    fr = head["frames"]
    mel = np.frombuffer(raw[9 + n: 9 + n + fr * 128], dtype="<f2").astype(np.float32).reshape(fr, 64)
    y = np.array(head["watch"], dtype=np.int64)
    ep = min(fr // 300, len(y))
    y = y[:ep].copy()
    sounds = head.get("soundFrames", [])
    M = norm_frames(torch.tensor(mel[: ep * 300].T), sounds)
    for a, b in sounds:
        y[int(a) // 300: int(np.ceil(b / 300))] = -1
    X = M.T.reshape(ep, 300, 64).permute(0, 2, 1).contiguous()
    return X, y, head


@torch.no_grad()
def predict(net, X):
    e = torch.cat([net.cnn(X[i:i + 200].to(dev).reshape(-1, 1, 64, 300)).reshape(-1, net.gru.input_size)
                   for i in range(0, len(X), 200)])
    out, _ = net.gru(e[None])
    return net.out(out)[0].argmax(-1).cpu().numpy()


def kappa(C):
    N = C.sum()
    po = np.trace(C) / N
    pe = (C.sum(0) * C.sum(1)).sum() / N / N
    return (po - pe) / (1 - pe)


def score(p, y):
    ok = y >= 0
    C = np.zeros((4, 4))
    np.add.at(C, (y[ok], p[ok]), 1)
    return dict(kappa=round(float(kappa(C)), 3), acc=round(float(np.trace(C) / C.sum()), 3), epochs=int(ok.sum()),
                minutes={k: int(((p == i) & ok).sum() / 2) for i, k in enumerate(NAMES)},
                watch_minutes={k: int((y == i).sum() / 2) for i, k in enumerate(NAMES)})


def main():
    folder, out, models = sys.argv[1], sys.argv[2], sys.argv[3:]
    nights = {}
    for f in sorted(glob.glob(os.path.join(folder, "*.suya"))):
        X, y, head = load(f)
        k = os.path.basename(f)[:8]
        nights[k] = (X, y)
        print("Nacht", k, len(y), "Epochen,", int((y >= 0).sum()), "mit Watch, Klang-Bereiche:",
              len(head.get("soundFrames", [])), "Gerät:", head.get("device", "?"), flush=True)
    res = {}
    for mp in models:
        name = os.path.basename(mp)[:-3]
        net = Net().to(dev)
        net.load_state_dict(torch.load(mp, map_location=dev))
        net.eval()
        res[name] = {}
        for k, (X, y) in nights.items():
            r = score(predict(net, X), y)
            res[name][k] = r
            print(name, k, r, flush=True)
        ks = [r["kappa"] for r in res[name].values()]
        print("MITTEL", name, "kappa %.3f" % np.mean(ks), "min %.3f" % np.min(ks), flush=True)
    json.dump(res, open(out, "w"), indent=1)
    print("TABELLE (Kappa)")
    print("Modell".ljust(28) + "".join(k.ljust(10) for k in nights) + "Mittel")
    for name, r in res.items():
        ks = [r[k]["kappa"] for k in nights]
        print(name.ljust(28) + "".join(("%.3f" % v).ljust(10) for v in ks) + "%.3f" % np.mean(ks))


if __name__ == "__main__":
    main()
