"""BES çıkış / stopaj hesapları (yerel kurallar)."""

from __future__ import annotations

from dataclasses import dataclass

# Hak edişe esas süre bu yıl ve üzerindeyse stopaj oranı düşer
HAK_EDIS_STOPAJ_ESIK_YIL = 10
STOPAJ_ORANI_KISA = 0.15
STOPAJ_ORANI_UZUN = 0.10


def stopaj_orani(hak_edise_esas_sure_yil: float) -> float:
    """Sözleşme hak edişe esas süre ≥ 10 yıl ise %10, aksi halde %15."""
    return STOPAJ_ORANI_UZUN if hak_edise_esas_sure_yil >= HAK_EDIS_STOPAJ_ESIK_YIL else STOPAJ_ORANI_KISA


def stopaj_kesintisi_tl(yatirim_getirisi_tl: float, hak_edise_esas_sure_yil: float) -> float:
    """Stopaj kesintisi = yatırım getirisi × uygulanan stopaj oranı."""
    return yatirim_getirisi_tl * stopaj_orani(hak_edise_esas_sure_yil)


@dataclass(frozen=True)
class CikisHesabi:
    """Çıkışta ele geçen tutar (güncel birikim) bileşenleri."""

    uygulanan_stopaj_orani: float
    stopaj_kesintisi_tl: float
    cikista_net_tl: float


def cikista_ele_gecen_tl(
    birikiminiz: float,
    hak_edis_tutariniz: float,
    yatirim_getiriniz: float,
    hak_edise_esas_sure_yil: float,
    *,
    devlet_katkili_sozlesme: bool = True,
) -> CikisHesabi:
    """
    Stopaj kesintisi = Yatırım getiriniz × stopaj oranı;
    stopaj oranı: süre ≥ 10 yıl → %10, değilse %15.

    **Devlet katkılı (varsayılan):** güncel birikim =
    Birikiminiz + Hak ediş tutarınız − stopaj.
    (Devlet katkısı toplamı bu formülde kullanılmaz; hak ediş tutarı devlet payından
    hak ettiğiniz kısmı temsil eder.)

    **Devlet katkısız sözleşme:** güncel birikim = Birikiminiz − stopaj.
    Bu durumda ``hak_edis_tutariniz`` hesaba katılmaz (çağıran 0.0 geçebilir).
    """
    oran = stopaj_orani(hak_edise_esas_sure_yil)
    sk = round(yatirim_getiriniz * oran, 2)
    if devlet_katkili_sozlesme:
        net = round(birikiminiz + hak_edis_tutariniz - sk, 2)
    else:
        net = round(birikiminiz - sk, 2)
    return CikisHesabi(
        uygulanan_stopaj_orani=oran,
        stopaj_kesintisi_tl=sk,
        cikista_net_tl=net,
    )


# ---------------------------------------------------------------------------
# Devlet katkısı hak ediş oranı (BES mevzuatı, EGM)
# ---------------------------------------------------------------------------
# Sistemde kalma süresine göre kademeli oran (yaş şartı dikkate alınmaz):
#   <  3 yıl  → %0
#   3–6 yıl  → %15
#   6–10 yıl → %35
#   ≥ 10 yıl → %60
# Not: Emeklilik (10 yıl + 56 yaş), vefat veya maluliyet durumunda %100 olur;
# bu fonksiyon yalnızca süre tabanlı oranı verir.

HAK_EDIS_KADEMELERI: tuple[tuple[float, float], ...] = (
    (3.0,   0.0),    # < 3 yıl  → %0
    (6.0,  15.0),    # 3–6 yıl  → %15
    (10.0, 35.0),    # 6–10 yıl → %35
    (float("inf"), 60.0),  # ≥ 10 yıl → %60
)


def hak_edis_orani_from_sure(sure_yil: float) -> float:
    """Devlet katkısı hak ediş oranı (yüzde olarak, ör. 60.0)."""
    for esik, oran in HAK_EDIS_KADEMELERI:
        if sure_yil < esik:
            return oran
    return HAK_EDIS_KADEMELERI[-1][1]


def hak_edis_tutari_from_oran(devlet_katkisi_tl: float, oran_yuzde: float) -> float:
    """Hak ediş tutarı = devlet katkısı × oran/100. Kuruşa yuvarlar."""
    return round(devlet_katkisi_tl * oran_yuzde / 100.0, 2)


def format_tl(n: float) -> str:
    """Basit TR gösterim (tam sayı kuruşlar için yeterli)."""
    s = f"{n:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")
