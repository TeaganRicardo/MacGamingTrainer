import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

/// A process-held lease for one module-declared target. The kernel lock is the
/// authority; the PID is only a best-effort hint for focusing the current owner.
final class TrainerTargetOwnership {
    enum Acquisition {
        case acquired(TrainerTargetOwnership)
        case occupied(ownerPID: Int32?)
    }

    private let descriptor: Int32

    private init(descriptor: Int32) {
        self.descriptor = descriptor
    }

    deinit {
        close(descriptor)
    }

    static func acquire(directory: URL, processName: String, bundleIdentifier: String) throws -> Acquisition {
        try FileManager.default.createDirectory(
            at: directory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        // Copies/versions of the Trainer share the target identity rather than
        // the Trainer's executable path or bundle ID. Process name is the
        // fallback for modules whose target has no app bundle identity.
        let identity = bundleIdentifier.isEmpty ? "process:\(processName)" : "bundle:\(bundleIdentifier)"
        let filename = Data(identity.utf8).base64EncodedString()
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "+", with: "-") + ".lock"
        let path = directory.appendingPathComponent(filename).path
        let descriptor = open(path, O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0o600)
        guard descriptor >= 0 else { throw posixError() }
        var retained = false
        defer { if !retained { close(descriptor) } }

        guard flock(descriptor, LOCK_EX | LOCK_NB) == 0 else {
            let code = errno
            guard code == EWOULDBLOCK || code == EAGAIN else { throw posixError(code) }
            var bytes = [UInt8](repeating: 0, count: 32)
            let count = pread(descriptor, &bytes, bytes.count, 0)
            let pid = count > 0 ? Int32(String(decoding: bytes.prefix(count), as: UTF8.self)
                .trimmingCharacters(in: .whitespacesAndNewlines)) : nil
            return .occupied(ownerPID: pid.flatMap { $0 > 0 ? $0 : nil })
        }

        // Never unlink the file: replacing its inode would let a concurrent
        // launcher acquire a different lock while the original owner is alive.
        // Stale metadata is overwritten only after kernel ownership is proven.
        guard ftruncate(descriptor, 0) == 0 else { throw posixError() }
        let data = Data("\(getpid())\n".utf8)
        let count = data.withUnsafeBytes { pwrite(descriptor, $0.baseAddress, $0.count, 0) }
        guard count == data.count else { throw posixError(count < 0 ? errno : EIO) }
        retained = true
        return .acquired(TrainerTargetOwnership(descriptor: descriptor))
    }

    private static func posixError(_ code: Int32 = errno) -> NSError {
        NSError(domain: NSPOSIXErrorDomain, code: Int(code))
    }
}
