import AppKit

let target = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: target, withIntermediateDirectories: true)
func color(_ r: CGFloat, _ g: CGFloat, _ b: CGFloat, _ a: CGFloat = 1) -> NSColor {
    NSColor(srgbRed: r, green: g, blue: b, alpha: a)
}
func drawIcon() {
    NSGraphicsContext.saveGraphicsState()
    let base = NSBezierPath(roundedRect: NSRect(x: 68, y: 68, width: 888, height: 888), xRadius: 200, yRadius: 200)
    let shadow = NSShadow(); shadow.shadowColor = color(0,0,0,0.28); shadow.shadowBlurRadius = 26; shadow.shadowOffset = NSSize(width: 0, height: -10); shadow.set()
    color(0.04,0.09,0.16).setFill(); base.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient(starting: color(0.035,0.075,0.14), ending: color(0.10,0.24,0.34))!.draw(in: base, angle: 42)
    color(0.52,0.78,0.93,0.18).setStroke(); base.lineWidth = 3; base.stroke()

    let pill = NSBezierPath(roundedRect: NSRect(x: 206, y: 372, width: 612, height: 288), xRadius: 144, yRadius: 144)
    NSGraphicsContext.saveGraphicsState()
    let glow = NSShadow(); glow.shadowColor = color(0.04,0.74,0.88,0.38); glow.shadowBlurRadius = 50; glow.shadowOffset = NSSize(width: 0, height: 0); glow.set()
    color(0.10,0.75,0.87).setFill(); pill.fill()
    NSGraphicsContext.restoreGraphicsState()
    NSGradient(starting: color(0.10,0.89,0.76), ending: color(0.12,0.60,0.95))!.draw(in: pill, angle: -12)
    color(0.70,1,1,0.45).setStroke(); pill.lineWidth = 3; pill.stroke()

    let power = NSBezierPath()
    power.appendArc(withCenter: NSPoint(x: 345, y: 510), radius: 45, startAngle: 135, endAngle: 405, clockwise: false)
    power.lineWidth = 20; power.lineCapStyle = .round
    color(0.025,0.23,0.29,0.9).setStroke(); power.stroke()
    let stem = NSBezierPath(); stem.move(to: NSPoint(x:345,y:570)); stem.line(to:NSPoint(x:345,y:523)); stem.lineWidth = 20; stem.lineCapStyle = .round; stem.stroke()

    let knob = NSBezierPath(ovalIn: NSRect(x: 548, y: 402, width: 228, height: 228))
    NSGraphicsContext.saveGraphicsState()
    let s = NSShadow(); s.shadowColor = color(0.02,0.22,0.39,0.35); s.shadowBlurRadius = 24; s.shadowOffset = NSSize(width:0,height:-10); s.set()
    NSColor.white.setFill(); knob.fill(); NSGraphicsContext.restoreGraphicsState()
    NSGradient(starting: color(0.80,0.96,1), ending: NSColor.white)!.draw(in: knob, angle: 70)
    color(1,1,1,0.8).setStroke(); knob.lineWidth=3; knob.stroke()

    let x: CGFloat = 662, y: CGFloat = 516, r: CGFloat = 53
    let star = NSBezierPath(); star.move(to:NSPoint(x:x,y:y+r))
    star.curve(to:NSPoint(x:x+r,y:y),controlPoint1:NSPoint(x:x+11,y:y+15),controlPoint2:NSPoint(x:x+15,y:y+11))
    star.curve(to:NSPoint(x:x,y:y-r),controlPoint1:NSPoint(x:x+15,y:y-11),controlPoint2:NSPoint(x:x+11,y:y-15))
    star.curve(to:NSPoint(x:x-r,y:y),controlPoint1:NSPoint(x:x-11,y:y-15),controlPoint2:NSPoint(x:x-15,y:y-11))
    star.curve(to:NSPoint(x:x,y:y+r),controlPoint1:NSPoint(x:x-15,y:y+11),controlPoint2:NSPoint(x:x-11,y:y+15)); star.close()
    NSGradient(starting:color(0.04,0.18,0.30),ending:color(0.04,0.47,0.55))!.draw(in:star,angle:45)

    let link = NSBezierPath(); link.move(to:NSPoint(x:390,y:270)); link.line(to:NSPoint(x:634,y:270)); link.lineWidth=10; link.lineCapStyle = .round
    color(0.31,0.66,0.79,0.60).setStroke(); link.stroke()
    for point in [390,512,634] {
        let node = NSBezierPath(ovalIn:NSRect(x:CGFloat(point)-17,y:253,width:34,height:34))
        (point == 512 ? color(0.31,0.95,0.82) : color(0.30,0.65,0.82)).setFill(); node.fill()
    }
}
for (name,size) in [("icon_16x16",16),("icon_16x16@2x",32),("icon_32x32",32),("icon_32x32@2x",64),("icon_128x128",128),("icon_128x128@2x",256),("icon_256x256",256),("icon_256x256@2x",512),("icon_512x512",512),("icon_512x512@2x",1024)] {
    let rep = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:size,pixelsHigh:size,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    let context = NSGraphicsContext(bitmapImageRep:rep)!
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = context
    context.cgContext.scaleBy(x:CGFloat(size)/1024,y:CGFloat(size)/1024)
    drawIcon(); context.flushGraphics(); NSGraphicsContext.restoreGraphicsState()
    try rep.representation(using:.png,properties:[:])!.write(to:target.appendingPathComponent(name+".png"))
}
