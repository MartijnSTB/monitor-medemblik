# Medemblik Monitor (prototype)

Gratis openbare monitor met GitHub Actions en GitHub Pages. Dit is een **prototype**, geen gegarandeerd volledige gemeentelijke publicatiefeed.

## Installatie zonder eigen computer

1. Maak een gratis GitHub account op https://github.com/.
2. Maak een **public** repository met naam `medemblik-monitor`.
3. Upload de inhoud van deze map naar de hoofdmap van de repository, inclusief de verborgen map `.github`. GitHub's webinterface ondersteunt uploaden van losse bestanden; gebruik desgewenst GitHub Codespaces om het ZIP bestand uit te pakken.
4. Ga naar **Settings → Actions → General → Workflow permissions** en kies **Read and write permissions**.
5. Ga naar **Actions → Monitor publicaties → Run workflow** om de eerste run te starten.
6. Ga naar **Settings → Pages → Build and deployment → Deploy from a branch**. Selecteer `main` en `/docs`, klik Save.
7. Open `https://JOUWGEBRUIKERSNAAM.github.io/medemblik-monitor/` nadat Pages is gepubliceerd.

## Bronnen

* https://www.medemblik.nl/nieuws
* https://www.medemblik.nl/raad-bestuur-en-organisatie/college-van-bw/collegebesluiten
* https://www.medemblik.nl/raad-bestuur-en-organisatie/klacht-bezwaar-en-informatieverzoek/openbare-informatie
* https://medemblik.bestuurlijkeinformatie.nl/
* https://www.medemblik.nl/raad-bestuur-en-organisatie/bekendmakingen/koop/pagina/2

## Beperkingen die belangrijk zijn

* Nieuws, Woo en raad worden in deze eerste versie als **linkinventaris** gevolgd. Wijzigingen in de inhoud van de achterliggende documenten worden nog niet herkend.
* Collegebesluiten worden via koppen en omliggende tekst gevolgd. Herhaalde titels kunnen samenvallen.
* Officiële bekendmakingen worden voorlopig via de gemeentelijke verwijspagina gevolgd, **niet** via de complete overheid.nl dataset.
* De eerste run markeert bestaande links als nieuw. `first_seen` is de detectietijd, niet de publicatietijd.
* Alleen de laatste 3000 records worden bewaard; Git geschiedenis is geen robuust versiearchief.
* GitHub Actions kan vertragen en geplande workflows in inactieve publieke repositories uitschakelen.
* Een openbare repository maakt de verzamelde data openbaar. Er worden geen wachtwoorden gebruikt.
* De site ververst na elke geslaagde workflow, maar geeft nog geen browser pushnotificaties.

## Vervolg

Voeg een echte SRU/Atom connector voor officiële bekendmakingen toe, documentdownload en hashes per bijlage, paginering en datumextractie, raadsportaal API indien beschikbaar, retry/backoff, en een historisch archief. Valideer elk bronresultaat voordat je op volledigheid vertrouwt.
