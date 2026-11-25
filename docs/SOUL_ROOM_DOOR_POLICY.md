# Portes des salles de combat lorsqu'une soul manque

Règle définie avec l'utilisateur le 23 novembre 2026.

**Statut : spécification du comportement voulu. Les changements du contrôle des
portes et des herses décrits ici ne sont pas encore implémentés.** L'audit et les
corrections de logique des souls constituent un travail distinct, déjà présent
dans les modifications locales.

## Condition d'application

Cette règle s'applique seulement lorsqu'au moins une soul nécessaire au combat
de la salle manque et que le combat n'est pas déjà terminé.

Une soul est nécessaire lorsqu'elle commande l'apparition d'un ennemi dont la
victoire dépend. Les ennemis qui restent volontairement présents sans soul ne
créent pas de soul requise supplémentaire.

Lorsque toutes les souls nécessaires sont présentes, le jeu retrouve son
fonctionnement normal : apparition des ennemis, déclenchement du combat,
verrouillage et déverrouillage natifs. Une salle déjà terminée reste terminée.
Cette règle ne modifie pas ses drapeaux de victoire.

## Définitions

- **Entrée** : passage effectivement emprunté par Link pour arriver dans la
  salle. C'est aussi le passage par lequel il doit pouvoir faire demi-tour.
- **Cul-de-sac** : salle qui ne possède aucun autre passage structurel pour
  continuer son parcours.
- **Salle traversante** : salle qui possède au moins une sortie distincte de
  l'entrée.
- **Porte** : élément que Link ouvre par interaction.
- **Herse violette** : obstacle de combat qui ferme un passage, avec sa collision.
- **Cadenas** : verrou indépendant qui utilise la clé native appropriée.

La classification porte sur les vrais passages. Deux herses placées de part et
d'autre d'une même porte ne représentent pas deux sorties. Un coffre n'est pas
une sortie ; un téléporteur créé seulement après la victoire ne rend pas à lui
seul la salle traversante. Les chutes, ascenseurs et passages à sens unique
doivent être identifiés explicitement avant de classer la salle.

## Comportement sans la soul nécessaire

| Situation | Entrer | Faire demi-tour | Continuer par une autre sortie |
|---|---|---|---|
| Cul-de-sac, porte sans cadenas | Porte visible et ouvrable par interaction | Même porte ouvrable, sans enfermement de combat | Sans objet |
| Cul-de-sac, cadenas et clé absente | Refus natif du cadenas | Aucun verrou de combat ajouté | Sans objet |
| Cul-de-sac, cadenas et bonne clé présente | Déverrouillage et consommation native de la clé, puis interaction normale | Retour possible après déverrouillage | Sans objet |
| Salle traversante | Entrée visible et utilisable, sous réserve du cadenas natif | Passage d'entrée utilisable | Chaque autre sortie est bloquée par sa herse violette |

Entrer ou ouvrir la porte d'entrée ne doit pas déclencher un enfermement de
combat lorsque la soul manque. La porte doit rester présente : masquer la porte
entière avec une condition d'apparition ne satisfait pas cette règle.

Dans une salle traversante, le blocage des sorties doit être réel et visible :
une herse sans collision ou une collision invisible ne satisfait pas la règle.
Le cadenas d'une sortie reste également indépendant. Posséder ou utiliser sa
clé ne doit pas contourner la herse de combat.

Si Link entre par un autre passage, ce passage devient son entrée pour cette
visite : il doit pouvoir repartir par là. Les autres passages restent les
sorties à bloquer tant que la soul nécessaire manque.

## Récompenses et logique

La règle autorise l'entrée et le repli, pas une victoire fictive.

- Aucun drapeau de combat terminé n'est écrit pour ouvrir l'entrée.
- Un coffre, une chanson, une plateforme ou une récompense qui demande la
  victoire conserve cette condition.
- Les objets réellement accessibles avant le combat peuvent être récupérés
  sans ajouter artificiellement la soul comme prérequis.
- La logique doit distinguer **entrer**, **récupérer un objet avant le combat**,
  **gagner le combat** et **traverser la salle**. La soul est requise pour les
  actions qui dépendent effectivement de la victoire.
- Une soul ne peut être placée derrière le combat ou la sortie qu'elle débloque.
  Les cycles enfant/adulte restent interdits.

Les prérequis conservateurs actuels à l'entrée des donjons ne constituent pas
encore cette modélisation par salle. Ils ne devront être assouplis qu'avec des
correspondances vérifiées entre passages, combats et récompenses.

## Restauration et persistance

Acquérir la dernière soul manquante restaure les conditions normales du combat,
sans inventer de nouveau déclencheur ni effacer une victoire antérieure. Les
cadenas déjà déverrouillés et les clés déjà consommées gardent leur état natif.

Une sauvegarde, un rechargement ou une nouvelle visite ne doit ni enfermer Link
sans moyen de combattre, ni ouvrir une sortie qui exige encore la victoire.

## Critères d'acceptation

1. Sans soul, entrer dans un cul-de-sac puis ressortir sans combattre ; la porte
   reste visible et les deux interactions fonctionnent.
2. Répéter avec un cadenas : refus sans clé, ouverture avec la bonne clé et
   débit natif unique ; un aller-retour ne consomme pas une deuxième clé.
3. Sans soul, entrer dans une salle traversante, constater les herses violettes
   sur les autres sorties et repartir par l'entrée.
4. Vérifier les deux sens d'entrée et les salles à plusieurs sorties ; aucun
   sens ne doit permettre de contourner le combat.
5. Vérifier qu'une collision invisible ne reste pas sur le passage de repli.
6. Avec plusieurs familles nécessaires, une seule soul manquante suffit à
   maintenir cette politique ; posséder une autre soul ne simule pas la victoire.
7. Confirmer que les récompenses postcombat et les drapeaux de victoire restent
   bloqués, alors qu'un objet réellement accessible avant combat reste accessible.
8. Avec toutes les souls, vérifier le déroulement natif complet du combat et
   l'ouverture de ses sorties après la victoire.
9. Répéter après sauvegarde/rechargement et après une victoire déjà enregistrée.
10. Faire rejouer la logique depuis les vrais objets de départ, en incluant le
    cas Song of Time dans la tombe royale et soul des Keese uniquement adulte.

## Contraintes pour l'implémentation

Les données natives séparent porte, herses latérales, cadenas et collision
(`PushAirWall_DoorFront`). Les modules observés possèdent notamment les
commandes latérales `LockPlusZ` et `LockMinusZ`. Leur association à un passage
doit être vérifiée pour chaque famille de contrôleurs.

Il faut agir sur le verrou de combat du bon côté, tout en conservant
l'interaction de la porte et la gestion native du cadenas. Un changement global
du module partagé ou une suppression générale des acteurs `*Shutter*` ne permet
pas de garantir ces distinctions.

Le nombre de compteurs ou de groupes IA ne prouve pas le nombre de sorties.
L'[inventaire des combats](SOUL_COMBAT_AUDIT.md) sert de point de départ ; il ne
constitue pas encore une cartographie vérifiée des entrées et sorties physiques.
