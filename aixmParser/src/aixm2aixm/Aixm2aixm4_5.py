#!/usr/bin/env python3

import bpaTools

class Aixm2aixm4_5:

    def __init__(self, oCtrl) -> None:
        bpaTools.initEvent(__file__, oCtrl.oLog)
        self.oCtrl = oCtrl
        self.cstXmlFileHeader:str = '<?xml version="1.0" encoding="UTF-8"?>\n'
        self.cstXmlTagRootName:str = ""
        return


    def cloneXmlHeader(self, sXmlTag, output) -> None:
        tagRoot = self.oCtrl.oAixm.root.find(sXmlTag).parent
        self.cstXmlTagRootName = tagRoot.name
        sTagRootHeader:str = "<" + self.cstXmlTagRootName
        for key,val in tagRoot.attrs.items():
            sTagRootHeader += ' ' + key + '="' + val + '"'
        sTagRootHeader += ">\n"
        output.write(self.cstXmlFileHeader)
        output.write(sTagRootHeader)
        return

    def copyNodes(self, sTitle, sXmlTag, sExtFile) -> None:
        sFilePath:str = bpaTools.getFilePath(self.oCtrl.srcFile)
        sFileName:str = bpaTools.getFileName(self.oCtrl.srcFile)
        sOutFile:str = sFilePath + sFileName + sExtFile + ".xml"
        bpaTools.deleteFile(sOutFile)

        sMsg = "Parsing {0} to Aixm4_5 - {1}".format(sXmlTag, sTitle)
        self.oCtrl.oLog.info(sMsg)

        sMsg = "Writing to Aixm4_5 file - {0}".format(sOutFile)
        self.oCtrl.oLog.info(sMsg)

        output = open(file=sOutFile, mode="a", encoding=self.oCtrl.sEncoding)   #Open a file for write only (append)
        oList = self.oCtrl.oAixm.root.find_all(sXmlTag, recursive=False)
        barre = bpaTools.ProgressBar(len(oList), 20, title=sMsg, isSilent=self.oCtrl.oLog.isSilent)
        self.cloneXmlHeader(sXmlTag, output)

        idx = 0
        for gbr in oList:
            idx+=1
            output.write(gbr.prettify())
            barre.update(idx)
        barre.reset()
        output.write("</" + self.cstXmlTagRootName + ">")
        output.close()
        return

