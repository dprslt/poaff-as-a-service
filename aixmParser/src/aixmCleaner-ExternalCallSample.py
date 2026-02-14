#!/usr/bin/env python3

import bpaTools
import aixmReader

if __name__ == '__main__':
    ### Context applicatif
    callingContext      = "Paragliding-OpenAir-French-Files"        #Your app calling context
    linkContext         = "http://pascal.bazile.free.fr/paraglidingFolder/divers/GPS/OpenAir-Format/"
    appName             = "aixmCleaner"                             #or your app name
    appPath             = bpaTools.getFilePath(__file__)            #or your app path
    appVersion          = bpaTools.getVersionFile()                 #or your app version
    appId               = appName + " v" + appVersion
    outPath             = appPath + "../out/"
    logFile             = outPath + "_" + appName + ".log"
    bpaTools.createFolder(outPath)                                  #Init dossier de sortie


    ####  Source test file  ####
    srcFile = "../tst/aixm4.5_SIA-FR_map-Airspaces.xml"
    #srcFile = "../tst/aixm4.5_SIA-FR_ctrl-Airspaces.xml"
    #srcFile = "../../poaff/input/Tests/99999999_BPa_Test4CleaningCatalog_aixm45.xml"
    #srcFile = "../../poaff/input/Tests/99999999_BPa_Test4AppendDelta1_aixm45.xml"
    #srcFile = "../../poaff/input/Tests/99999999_BPa_Test4AppendDelta2_aixm45.xml"
    #srcFile = "../../poaff/input/Tests/99999999_BPa_TestBORDERs_aixm45.xml"
    #srcFile = "../../poaff/input/Tests/99999999_BPa_Test4Circles_Arcs_aixm45.xml"
    #srcFile = "../../poaff/input/Tests/99999999_BPa_Test4ZonesWithArc.xml"
    #srcFile = "../../poaff/input/Tests/99999999_BPa_TestGroundEstimatedHeight_aixm45.xml"
    #srcFile = "../../poaff/output/Tests/map/99999999_ComplexArea_aixm45.xml"

    #### 4POAFF - Tests for real bigData files ####
    #srcFile = "../../poaff/input/SIA/20231005_AIRAC-1023_aixm4.5_SIA-FR.xml.xml"
    srcFile = "../../poaff/input/EuCtrl/20231005_AIRAC-1023_aixm4.5_Eurocontrol-Euro.xml"
    #srcFile = "../../poaff/input/EuCtrl/20231005_AIRAC-1023_aixm4.5_Eurocontrol-Monde.xml" --> Fichier impossible a traiter // 'MemoryError' en cours de lecture

    #### Context d'appel
    #aArgv = [appName, srcFile, aixmReader.CONST.frmtAIXM45, aixmReader.CONST.typeCTRLTOWERS]
    #aArgv = [appName, srcFile, aixmReader.CONST.frmtAIXM45, aixmReader.CONST.typeAERODROMES]
    #aArgv = [appName, srcFile, aixmReader.CONST.frmtAIXM45, aixmReader.CONST.typeOBSTACLES]
    #aArgv = [appName, srcFile, aixmReader.CONST.frmtAIXM45, aixmReader.CONST.typeRUNWAYCENTER]
    #aArgv = [appName, srcFile, aixmReader.CONST.frmtAIXM45, aixmReader.CONST.typeGATESTANDS]
    #aArgv = [appName, srcFile, aixmReader.CONST.frmtAIXM45, aixmReader.CONST.typeGEOBORDER]
    #aArgv = [appName, srcFile, aixmReader.CONST.frmtAIXM45, aixmReader.CONST.typeAIRSPACES]
    aArgv = [appName, srcFile, aixmReader.CONST.frmtAIXM45, aixmReader.CONST.typeGEOBORDER, aixmReader.CONST.typeAIRSPACES]

    ####  Préparation d'appel ####
    oOpts = bpaTools.getCommandLineOptions(aArgv)           #Arguments en dictionnaire

    oLog = bpaTools.Logger(appId, logFile, callingContext, linkContext, debugLevel=1, isSilent=bool(aixmReader.CONST.optSilent in oOpts))
    oLog.resetFile()                                        #Clean du log si demandé
    oLog.writeCommandLine(aArgv)                            #Trace le contexte d'execution
    aixmCtrl = aixmReader.AixmControler(srcFile, outPath, "", oLog=oLog)	    #Init controler
    if aixmCtrl.execCleaner(oOpts):                                              #Execution des traitements
        print()
        if oLog.CptCritical or oLog.CptError:
            print("/!\ Processing Error(s)")
    oLog.Report()
    oLog.closeFile()

