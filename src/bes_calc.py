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


def format_tl(n: float) -> str:
    """Basit TR gösterim (tam sayı kuruşlar için yeterli)."""
    s = f"{n:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")
