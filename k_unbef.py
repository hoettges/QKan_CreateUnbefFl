# -*- coding: utf-8 -*-

'''

  Import from HE
  ==============
  
  Aus einer Hystem-Extran-Datenbank im Firebird-Format werden Kanaldaten
  in die QKan-Datenbank importiert. Dazu wird eine Projektdatei erstellt,
  die verschiedene thematische Layer erzeugt, u.a. eine Klassifizierung
  der Schachttypen.
  
  | Dateiname            : import_from_he.py
  | Date                 : September 2016
  | Copyright            : (C) 2016 by Joerg Hoettges
  | Email                : hoettges@fh-aachen.de
  | git sha              : $Format:%H$
  
  This program is free software; you can redistribute it and/or modify   
  it under the terms of the GNU General Public License as published by   
  the Free Software Foundation; either version 2 of the License, or      
  (at your option) any later version.

'''

__author__ = 'Joerg Hoettges'
__date__ = 'September 2016'
__copyright__ = '(C) 2016, Joerg Hoettges'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = ':%H$'


import os, time

from QKan_Database.dbfunc import DBConnection

# import tempfile
import glob, shutil

from qgis.core import QgsFeature, QgsGeometry, QgsMessageLog, QgsProject, QgsCoordinateReferenceSystem
from PyQt4.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QFileInfo
from PyQt4.QtGui import QAction, QIcon

from qgis.utils import iface
from qgis.gui import QgsMessageBar, QgsMapCanvas, QgsLayerTreeMapCanvasBridge
import codecs
import pyspatialite.dbapi2 as splite
import xml.etree.ElementTree as ET
import logging

logger = logging.getLogger('QKan')

# Fortschritts- und Fehlermeldungen

def fortschritt(text,prozent):
    logger.debug(u'{:s} ({:.0f}%)'.format(text,prozent*100))
    QgsMessageLog.logMessage(u'{:s} ({:.0f}%)'.format(text,prozent*100), 'Export: ', QgsMessageLog.INFO)

def fehlermeldung(title, text):
    logger.debug(u'{:s} {:s}'.format(title,text))
    QgsMessageLog.logMessage(u'{:s} {:s}'.format(title, text), level=QgsMessageLog.CRITICAL)

# ------------------------------------------------------------------------------
# Hauptprogramm

def createUnbefFlaechen(database_QKan, liste_tezg, dbtyp = 'SpatiaLite'):

    '''Import der Kanaldaten aus einer HE-Firebird-Datenbank und Schreiben in eine QKan-SpatiaLite-Datenbank.

    :database_QKan: Datenbankobjekt, das die Verknüpfung zur QKan-SpatiaLite-Datenbank verwaltet.
    :type database: DBConnection (geerbt von dbapi...)

    :liste_tezg:    Liste der bei der Bearbeitung zu berücksichtigenden Haltungsflächen (tezg)
    :type:          list

    :dbtyp:         Typ der Datenbank (SpatiaLite, PostGIS)
    :type dbtyp:    String
    
    :returns: void
    '''

    # ------------------------------------------------------------------------------
    # Datenbankverbindungen

    dbQK = DBConnection(dbname=database_QKan)      # Datenbankobjekt der QKan-Datenbank zum Schreiben

    if dbQK is None:
        fehlermeldung("Fehler", u'QKan-Datenbank {:s} wurde nicht gefunden!\nAbbruch!'.format(database_QKan))
        iface.messageBar().pushMessage("Fehler", u'QKan-Datenbank {:s} wurde nicht gefunden!\nAbbruch!'.format( \
            database_QKan), level=QgsMessageBar.CRITICAL)
        return None

    # Für die Erzeugung der Restflächen reicht eine SQL-Abfrage aus. 

    if len(liste_tezg) == 0:
        auswahl = ''
    elif len(liste_tezg) == 1:
        auswahl = ' AND'
    elif len(liste_tezg) == 2:
        auswahl = ' AND ('
    else:
        fehlermeldung("Interner Fehler","Fehler in Fallunterscheidung!")

    first = True
    for attr in liste_tezg:
        if first:
            first = False
            auswahl += """ (tezg.abflussparameter = '{abflussparameter}' AND
                            tezg.teilgebiet = '{teilgebiet}')""".format(abflussparameter = attr[0], teilgebiet = attr[1])
        else:   
            auswahl += """ OR\n      (tezg.abflussparameter = '{abflussparameter}' AND
                            tezg.teilgebiet = '{teilgebiet}')""".format(abflussparameter = attr[0], teilgebiet = attr[1])

    if len(liste_tezg) == 2:
        auswahl += """)"""

    sql = """WITH flbef AS (
            SELECT 'fldur_' || tezg.flnam AS flnam, 
              tezg.haltnam AS haltnam, tezg.neigkl AS neigkl, 
              tezg.regenschreiber AS regenschreiber, tezg.teilgebiet AS teilgebiet,
              tezg.abflussparameter AS abflussparameter,
              'Erzeugt mit Plugin Erzeuge unbefestigte Flaechen' AS kommentar, 
              tezg.geom AS geot, 
              GUnion(CastToMultiPolygon(Intersection(flaechen.geom,tezg.geom))) AS geob
            FROM tezg
            INNER JOIN flaechen
            ON Intersects(tezg.geom,flaechen.geom)
            WHERE 'fldur_' || tezg.flnam not in (SELECT flnam FROM flaechen)
              {auswahl}
            GROUP BY tezg.pk)
            INSERT INTO flaechen (flnam, haltnam, neigkl, regenschreiber, teilgebiet, abflussparameter, kommentar, geom) 
             SELECT 'fldur_' || flnam AS flnam, haltnam, neigkl, regenschreiber, teilgebiet, abflussparameter,
            kommentar, CastToMultiPolygon(Difference(geot,geob)) AS geom FROM flbef""".format(auswahl=auswahl)

    try:
        dbQK.sql(sql)
        dbQK.commit()
    except:
        fehlermeldung(u"SQL-Fehler in QKan_CreateUnbefFl: \n", sql)
        del dbQK
        return False

    del dbQK

    # Karte aktualisieren
    iface.mapCanvas().refreshAllLayers()


    iface.mainWindow().statusBar().clearMessage()
    iface.messageBar().pushMessage(u"Information", u"Restflächen sind erstellt!", level=QgsMessageBar.INFO)
    QgsMessageLog.logMessage(u"\nRestflächen sind erstellt!", level=QgsMessageLog.INFO)
