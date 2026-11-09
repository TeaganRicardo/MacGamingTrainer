import SwiftUI

/// Hades I meta-currency identities. The resource id is the authority; the
/// system symbol is only a compact discovery fallback while visible rows use
/// simplified vector silhouettes derived from the in-game resource outlines.
enum HadesResourceIcon {
    fileprivate enum Kind {
        case darkness, gemstones, chthonicKey, nectar, diamond, ambrosia, titanBlood
    }

    private static func kind(for resourceID: String) -> Kind? {
        switch resourceID {
        case "MetaPoints": .darkness
        case "Gems": .gemstones
        case "LockKeys": .chthonicKey
        case "GiftPoints": .nectar
        case "SuperGems": .diamond
        case "SuperGiftPoints": .ambrosia
        case "SuperLockKeys": .titanBlood
        default: nil
        }
    }

    static func systemName(for resourceID: String) -> String {
        switch resourceID {
        case "MetaPoints": "drop.fill"
        case "Gems": "diamond.fill"
        case "LockKeys": "key.fill"
        case "GiftPoints": "waterbottle.fill"
        case "SuperGems": "seal.fill"
        case "SuperGiftPoints": "wineglass.fill"
        case "SuperLockKeys": "drop.circle.fill"
        default: TrainerSemanticIcon.Concept.item
        }
    }

    static func glyph(for resourceID: String) -> TrainerGlyph {
        guard let kind = kind(for: resourceID) else {
            return .system(TrainerSemanticIcon.Concept.item)
        }
        return TrainerGlyph {
            HadesResourceGlyphShape(kind: kind)
                .padding(1)
        }
    }
}

/// Monochrome silhouettes intentionally preserve only the recognition-bearing
/// outline: crystal/drop, gem cluster, key, bottles, diamond and blood vial.
/// They do not reproduce Supergiant's textures, colors or internal artwork.
private struct HadesResourceGlyphShape: Shape {
    let kind: HadesResourceIcon.Kind

    func path(in rect: CGRect) -> Path {
        func point(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: rect.minX + rect.width * x, y: rect.minY + rect.height * y)
        }
        func polygon(_ points: [(CGFloat, CGFloat)], into path: inout Path) {
            guard let first = points.first else { return }
            path.move(to: point(first.0, first.1))
            for value in points.dropFirst() { path.addLine(to: point(value.0, value.1)) }
            path.closeSubpath()
        }

        var path = Path()
        switch kind {
        case .darkness:
            polygon([(0.50, 0.03), (0.78, 0.27), (0.86, 0.54), (0.69, 0.86),
                     (0.49, 0.98), (0.24, 0.80), (0.14, 0.48), (0.29, 0.20)], into: &path)

        case .gemstones:
            polygon([(0.18, 0.39), (0.34, 0.20), (0.55, 0.25), (0.63, 0.47),
                     (0.47, 0.67), (0.26, 0.62)], into: &path)
            polygon([(0.47, 0.50), (0.66, 0.34), (0.88, 0.43), (0.91, 0.67),
                     (0.74, 0.84), (0.52, 0.76)], into: &path)
            polygon([(0.14, 0.65), (0.29, 0.55), (0.45, 0.68), (0.42, 0.88),
                     (0.22, 0.94), (0.08, 0.82)], into: &path)

        case .chthonicKey:
            path.addEllipse(in: CGRect(x: rect.minX + rect.width * 0.05,
                                       y: rect.minY + rect.height * 0.22,
                                       width: rect.width * 0.43,
                                       height: rect.height * 0.43))
            path.addRect(CGRect(x: rect.minX + rect.width * 0.38,
                                y: rect.minY + rect.height * 0.40,
                                width: rect.width * 0.53,
                                height: rect.height * 0.16))
            path.addRect(CGRect(x: rect.minX + rect.width * 0.72,
                                y: rect.minY + rect.height * 0.53,
                                width: rect.width * 0.10,
                                height: rect.height * 0.19))
            path.addRect(CGRect(x: rect.minX + rect.width * 0.84,
                                y: rect.minY + rect.height * 0.53,
                                width: rect.width * 0.08,
                                height: rect.height * 0.13))

        case .nectar:
            polygon([(0.38, 0.08), (0.62, 0.08), (0.62, 0.23), (0.70, 0.30),
                     (0.82, 0.48), (0.78, 0.82), (0.65, 0.94), (0.35, 0.94),
                     (0.22, 0.82), (0.18, 0.48), (0.30, 0.30), (0.38, 0.23)], into: &path)
            path.addEllipse(in: CGRect(x: rect.minX + rect.width * 0.18,
                                       y: rect.minY + rect.height * 0.18,
                                       width: rect.width * 0.23,
                                       height: rect.height * 0.20))
            path.addEllipse(in: CGRect(x: rect.minX + rect.width * 0.59,
                                       y: rect.minY + rect.height * 0.18,
                                       width: rect.width * 0.23,
                                       height: rect.height * 0.20))

        case .diamond:
            polygon([(0.18, 0.28), (0.38, 0.08), (0.65, 0.08), (0.84, 0.29),
                     (0.72, 0.58), (0.50, 0.94), (0.28, 0.58)], into: &path)

        case .ambrosia:
            polygon([(0.40, 0.04), (0.60, 0.04), (0.63, 0.23), (0.72, 0.31),
                     (0.77, 0.46), (0.72, 0.83), (0.61, 0.96), (0.39, 0.96),
                     (0.28, 0.83), (0.23, 0.46), (0.28, 0.31), (0.37, 0.23)], into: &path)
            path.addEllipse(in: CGRect(x: rect.minX + rect.width * 0.17,
                                       y: rect.minY + rect.height * 0.46,
                                       width: rect.width * 0.18,
                                       height: rect.height * 0.28))
            path.addEllipse(in: CGRect(x: rect.minX + rect.width * 0.65,
                                       y: rect.minY + rect.height * 0.46,
                                       width: rect.width * 0.18,
                                       height: rect.height * 0.28))

        case .titanBlood:
            polygon([(0.31, 0.23), (0.67, 0.23), (0.72, 0.38), (0.79, 0.53),
                     (0.72, 0.88), (0.61, 0.97), (0.36, 0.97), (0.24, 0.88),
                     (0.20, 0.54), (0.27, 0.38)], into: &path)
            path.addRect(CGRect(x: rect.minX + rect.width * 0.29,
                                y: rect.minY + rect.height * 0.14,
                                width: rect.width * 0.40,
                                height: rect.height * 0.13))
            path.addEllipse(in: CGRect(x: rect.minX + rect.width * 0.68,
                                       y: rect.minY + rect.height * 0.03,
                                       width: rect.width * 0.16,
                                       height: rect.height * 0.16))
            path.addEllipse(in: CGRect(x: rect.minX + rect.width * 0.82,
                                       y: rect.minY + rect.height * 0.17,
                                       width: rect.width * 0.09,
                                       height: rect.height * 0.09))
        }
        return path
    }
}
