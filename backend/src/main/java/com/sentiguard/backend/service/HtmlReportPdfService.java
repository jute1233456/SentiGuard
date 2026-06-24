package com.sentiguard.backend.service;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Entities;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import com.openhtmltopdf.pdfboxout.PdfRendererBuilder;

@Service
public class HtmlReportPdfService {

    private static final String FONT_FAMILY = "SentiGuardCJK";

    public byte[] renderPdf(String reportContent) {
        if (!StringUtils.hasText(reportContent)) {
            throw new IllegalArgumentException("核查报告内容为空，无法导出 PDF");
        }
        try (ByteArrayOutputStream outputStream = new ByteArrayOutputStream()) {
            PdfRendererBuilder builder = new PdfRendererBuilder();
            builder.useFastMode();
            registerChineseFonts(builder);
            builder.withHtmlContent(toXhtml(wrapHtmlIfNeeded(reportContent)), null);
            builder.toStream(outputStream);
            builder.run();
            return outputStream.toByteArray();
        } catch (Exception ex) {
            throw new IllegalStateException("PDF 报告生成失败：" + ex.getMessage(), ex);
        }
    }

    private void registerChineseFonts(PdfRendererBuilder builder) {
        for (Path fontPath : candidateFontPaths()) {
            if (Files.isRegularFile(fontPath)) {
                builder.useFont(fontPath.toFile(), FONT_FAMILY);
                return;
            }
        }
    }

    private List<Path> candidateFontPaths() {
        List<Path> paths = new ArrayList<>();
        addClasspathFont(paths, "fonts/NotoSansCJKsc-Regular.otf");
        addClasspathFont(paths, "fonts/SourceHanSansCN-Regular.otf");
        addClasspathFont(paths, "fonts/SimSun.ttf");
        addClasspathFont(paths, "fonts/simsun.ttc");

        String windir = System.getenv("WINDIR");
        if (StringUtils.hasText(windir)) {
            Path fonts = Paths.get(windir, "Fonts");
            paths.add(fonts.resolve("msyh.ttc"));
            paths.add(fonts.resolve("msyh.ttf"));
            paths.add(fonts.resolve("simhei.ttf"));
            paths.add(fonts.resolve("simsun.ttc"));
        }

        paths.add(Paths.get("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"));
        paths.add(Paths.get("/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf"));
        paths.add(Paths.get("/usr/share/fonts/truetype/arphic/uming.ttc"));
        paths.add(Paths.get("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"));
        return paths;
    }

    private void addClasspathFont(List<Path> paths, String resourcePath) {
        URL resource = getClass().getClassLoader().getResource(resourcePath);
        if (resource != null && "file".equalsIgnoreCase(resource.getProtocol())) {
            paths.add(new File(resource.getFile()).toPath());
        }
    }


    private String toXhtml(String html) {
        Document document = Jsoup.parse(html);
        document.outputSettings()
                .syntax(Document.OutputSettings.Syntax.xml)
                .escapeMode(Entities.EscapeMode.xhtml)
                .charset("UTF-8")
                .prettyPrint(false);
        return document.html();
    }
    private String wrapHtmlIfNeeded(String reportContent) {
        String normalized = reportContent.trim();
        String lower = normalized.toLowerCase(Locale.ROOT);
        String baseStyle = buildBaseStyle();
        if (lower.contains("<html")) {
            if (lower.contains("</head>")) {
                return normalized.replaceFirst("(?i)</head>", baseStyle + "</head>");
            }
            return normalized.replaceFirst("(?i)<html([^>]*)>", "<html$1><head>" + baseStyle + "</head>");
        }
        return "<!DOCTYPE html><html><head><meta charset=\"UTF-8\">" + baseStyle
                + "</head><body>" + normalized + "</body></html>";
    }

    private String buildBaseStyle() {
        return "<style>"
                + "@page{size:A4;margin:22mm 18mm;}"
                + "*{box-sizing:border-box;}"
                + "body{font-family:'" + FONT_FAMILY + "','Microsoft YaHei','SimSun',sans-serif;"
                + "color:#102a3b;line-height:1.72;font-size:13px;background:#fff;}"
                + "h1,h2,h3{color:#07324d;line-height:1.35;margin:0 0 12px;}"
                + "h1{font-size:24px;border-bottom:2px solid #1b7f8a;padding-bottom:10px;margin-bottom:18px;}"
                + "h2{font-size:18px;margin-top:22px;border-left:4px solid #1b7f8a;padding-left:10px;}"
                + "h3{font-size:15px;margin-top:16px;}"
                + "p{margin:8px 0;}ul,ol{padding-left:22px;}li{margin:6px 0;}"
                + "table{width:100%;border-collapse:collapse;margin:12px 0;}"
                + "th,td{border:1px solid #d8e4ed;padding:8px;vertical-align:top;}"
                + "th{background:#eef6fa;color:#234e6c;}"
                + "a{color:#1b6f9b;text-decoration:none;word-break:break-all;}"
                + ".report,.card,section{page-break-inside:auto;}"
                + "</style>";
    }
}