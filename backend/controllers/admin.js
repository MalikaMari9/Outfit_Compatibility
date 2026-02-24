import user from "../models/user.js";
import feedbackReport from "../models/feedbackReport.js";
import { verifyToken } from "../utils/jwt.js";
import { isValidObjectId } from "mongoose";

const VALID_REPORT_STATUS = new Set(["pending", "resolved", "dismissed"]);
const VALID_REPORT_PAGES = new Set(["mixmatch", "glowup", "compatibility", "recommend", "other"]);

const requireAdmin = async (req, res) => {
  const authHeader = req.headers.authorization;
  if (!authHeader) {
    res.status(401).json({ message: "Unauthorized access" });
    return null;
  }

  const decoded = await verifyToken(authHeader);
  if (!decoded) {
    res.status(401).json({ message: "Unauthorized access" });
    return null;
  }

  const adminUser = await user.findById(decoded.id).select("_id role");
  if (!adminUser || adminUser.role !== "admin") {
    res.status(403).json({ message: "Forbidden" });
    return null;
  }

  return adminUser;
};

const normalizeReportStatus = (value) => {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw || raw === "all") return "";
  return VALID_REPORT_STATUS.has(raw) ? raw : "";
};

const normalizeReportPage = (value) => {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw || raw === "all") return "";
  return VALID_REPORT_PAGES.has(raw) ? raw : "";
};

const escapeRegex = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const mapReport = (doc) => {
  const report = doc?.toObject ? doc.toObject() : doc;
  const reporter = report?.userId && typeof report.userId === "object" ? report.userId : null;

  return {
    _id: report?._id,
    page: report?.page || "other",
    message: report?.message || "",
    status: report?.status || "pending",
    details: report?.details || {},
    createdAt: report?.createdAt || null,
    updatedAt: report?.updatedAt || null,
    user: reporter
      ? {
          _id: reporter._id || null,
          name: reporter.name || "Unknown User",
          email: reporter.email || "",
        }
      : null,
  };
};

export const getAdminUsers = async (req, res) => {
  try {
    const adminUser = await requireAdmin(req, res);
    if (!adminUser) return;

    const page = Math.max(parseInt(req.query.page, 10) || 1, 1);
    const limit = Math.max(parseInt(req.query.limit, 10) || 6, 1);
    const skip = (page - 1) * limit;

    const [users, total] = await Promise.all([
      user
        .find({}, "-password")
        .sort({ createdAt: -1 })
        .skip(skip)
        .limit(limit),
      user.countDocuments(),
    ]);

    const normalized = users.map((u) => ({
      ...u.toObject(),
      role: u.role || "user",
    }));

    return res.status(200).json({
      users: normalized,
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit),
    });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ message: "Server error" });
  }
};

export const getAdminUserById = async (req, res) => {
  try {
    const adminUser = await requireAdmin(req, res);
    if (!adminUser) return;

    const { id } = req.params;
    if (!isValidObjectId(id)) {
      return res.status(400).json({ message: "Invalid user id" });
    }

    const targetUser = await user.findById(id).select("-password");
    if (!targetUser) {
      return res.status(404).json({ message: "User not found" });
    }

    const normalized = { ...targetUser.toObject(), role: targetUser.role || "user" };
    return res.status(200).json({ user: normalized });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ message: "Server error" });
  }
};

export const updateAdminUser = async (req, res) => {
  try {
    const adminUser = await requireAdmin(req, res);
    if (!adminUser) return;

    const { id } = req.params;
    if (!isValidObjectId(id)) {
      return res.status(400).json({ message: "Invalid user id" });
    }

    const { name, email, role, bio } = req.body;
    const updateData = {};

    if (name !== undefined) updateData.name = name;
    if (email !== undefined) updateData.email = email;
    if (bio !== undefined) updateData.bio = bio;
    if (role !== undefined) {
      const normalizedRole = role || "user";
      if (!["admin", "user"].includes(normalizedRole)) {
        return res.status(400).json({ message: "Invalid role" });
      }
      updateData.role = normalizedRole;
    }

    if (Object.keys(updateData).length === 0) {
      return res.status(400).json({ message: "No fields to update" });
    }

    const updatedUser = await user
      .findByIdAndUpdate(id, updateData, { new: true })
      .select("-password");
    if (!updatedUser) {
      return res.status(404).json({ message: "User not found" });
    }

    const normalized = { ...updatedUser.toObject(), role: updatedUser.role || "user" };
    return res.status(200).json({ user: normalized });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ message: "Server error" });
  }
};

export const deleteAdminUser = async (req, res) => {
  try {
    const adminUser = await requireAdmin(req, res);
    if (!adminUser) return;

    const { id } = req.params;
    if (!isValidObjectId(id)) {
      return res.status(400).json({ message: "Invalid user id" });
    }

    if (adminUser._id.toString() === id) {
      return res.status(400).json({ message: "Cannot delete your own account" });
    }

    const deletedUser = await user.findByIdAndDelete(id).select("-password");
    if (!deletedUser) {
      return res.status(404).json({ message: "User not found" });
    }

    return res.status(200).json({ message: "User deleted" });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ message: "Server error" });
  }
};

export const getAdminReports = async (req, res) => {
  try {
    const adminUser = await requireAdmin(req, res);
    if (!adminUser) return;

    const page = Math.max(parseInt(req.query.page, 10) || 1, 1);
    const limit = Math.min(Math.max(parseInt(req.query.limit, 10) || 25, 1), 200);
    const skip = (page - 1) * limit;
    const status = normalizeReportStatus(req.query.status);
    const reportPage = normalizeReportPage(req.query.category || req.query.page_key || req.query.pageName);
    const search = String(req.query.search || "").trim();

    const filter = {};
    if (status) filter.status = status;
    if (reportPage) filter.page = reportPage;
    if (search) {
      const regex = new RegExp(escapeRegex(search), "i");
      filter.$or = [{ message: regex }, { page: regex }];
    }

    const [reports, total] = await Promise.all([
      feedbackReport
        .find(filter)
        .populate("userId", "name email")
        .sort({ createdAt: -1 })
        .skip(skip)
        .limit(limit),
      feedbackReport.countDocuments(filter),
    ]);

    return res.status(200).json({
      reports: reports.map(mapReport),
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit),
    });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ message: "Server error" });
  }
};

export const getAdminReportById = async (req, res) => {
  try {
    const adminUser = await requireAdmin(req, res);
    if (!adminUser) return;

    const { id } = req.params;
    if (!isValidObjectId(id)) {
      return res.status(400).json({ message: "Invalid report id" });
    }

    const report = await feedbackReport.findById(id).populate("userId", "name email");
    if (!report) {
      return res.status(404).json({ message: "Report not found" });
    }

    return res.status(200).json({ report: mapReport(report) });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ message: "Server error" });
  }
};

export const updateAdminReport = async (req, res) => {
  try {
    const adminUser = await requireAdmin(req, res);
    if (!adminUser) return;

    const { id } = req.params;
    if (!isValidObjectId(id)) {
      return res.status(400).json({ message: "Invalid report id" });
    }

    const status = normalizeReportStatus(req.body?.status);
    if (!status) {
      return res.status(400).json({ message: "Invalid report status" });
    }

    const adminNoteRaw = String(req.body?.admin_note ?? req.body?.note ?? "").trim();
    const updateFields = {
      status,
      "details.admin_updated_at": new Date(),
      "details.admin_updated_by": adminUser._id,
    };

    if (adminNoteRaw) {
      updateFields["details.admin_note"] = adminNoteRaw.slice(0, 1000);
    }

    const updated = await feedbackReport
      .findByIdAndUpdate(id, { $set: updateFields }, { new: true })
      .populate("userId", "name email");

    if (!updated) {
      return res.status(404).json({ message: "Report not found" });
    }

    return res.status(200).json({ report: mapReport(updated) });
  } catch (err) {
    console.error(err);
    return res.status(500).json({ message: "Server error" });
  }
};
