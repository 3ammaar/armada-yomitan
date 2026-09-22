import { ButtonItem, ConfirmModal, DropdownItem, PanelSection, PanelSectionRow, TextField, ToggleField, showModal, staticClasses } from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useEffect, useRef, useState } from "react";
import { FaLanguage } from "react-icons/fa";
// Every text comes from the app's strings.py: this module is generated from it by tools/build_all.py.
import * as S from "./strings";

// The backend (main.py) answers launch and stop with {ok, message}; the message is what is shown.
type Answer = { ok: boolean; message: string };
const launch = callable<[], Answer>("launch");
const stop = callable<[], Answer>("stop");

// Installing the system packages (as root, by the backend) together with the app's own parts.
type Dependency = { name: string; optional: boolean; present: boolean };
type Dependencies = { ok: boolean; message: string; packages: Dependency[] };
type InstallStatus = { running: boolean; done: boolean; ok: boolean | null; line: string; message: string };
const getDependencies = callable<[], Dependencies>("get_dependencies");
const installDependencies = callable<[], Answer>("install_dependencies");
const installStatus = callable<[], InstallStatus>("install_status");

// The Advanced Settings: the backend says which settings there are and how to draw them; it stores them and passes them to the app.
type Value = string | boolean;
type Option = { key: string; kind: "choice" | "text" | "number" | "decimal" | "toggle"; choices: string[] };
type Settings = { values: Record<string, Value>; options: Option[] };
const getSettings = callable<[], Settings>("get_settings");
const setSettings = callable<[values: Record<string, Value>], Settings>("set_settings");
const resetSettings = callable<[], Settings>("reset_settings");

const LABELS: Record<string, string> = {
  rotation: S.DECKY_OPT_ROTATION,
  touch: S.DECKY_OPT_TOUCH,
  node: S.DECKY_OPT_NODE,
  mode: S.DECKY_OPT_MODE,
  engine: S.DECKY_OPT_ENGINE,
  scan_length: S.DECKY_OPT_SCAN_LENGTH,
  ui_scale: S.DECKY_OPT_UI_SCALE,
  no_grab: S.DECKY_OPT_NO_GRAB,
};
const CHOICES: Record<string, Record<string, string>> = {
  mode: { screen: S.DECKY_MODE_SCREEN, tap: S.DECKY_MODE_TAP, manual: S.DECKY_MODE_MANUAL },
  engine: { auto: S.DECKY_ENGINE_AUTO, rapidocr: S.DECKY_ENGINE_RAPIDOCR, tesseract: S.DECKY_ENGINE_TESSERACT },
};
const choiceLabel = (key: string, choice: string) =>
  key === "rotation" ? S.DECKY_DEGREES.replace("{degrees}", choice) : (CHOICES[key] || {})[choice] || choice;

const typed = (kind: Option["kind"], text: string) =>
  kind === "number" ? text.replace(/\D/g, "") : kind === "decimal" ? text.replace(/[^\d.]/g, "") : text;

function Advanced({ onBack }: { onBack: () => void }) {
  const [settings, setLocal] = useState<Settings | null>(null);
  useEffect(() => {
    getSettings().then(setLocal);
  }, []);

  const change = (key: string, value: Value) => {
    if (!settings) return;
    const values = { ...settings.values, [key]: value };
    setLocal({ ...settings, values });
    setSettings(values);
  };

  return (
    <PanelSection title={S.DECKY_ADVANCED}>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={onBack}>
          {S.DECKY_BACK}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" description={S.DECKY_APPLIES_NEXT_LAUNCH} onClick={() => resetSettings().then(setLocal)}>
          {S.DECKY_DEFAULT}
        </ButtonItem>
      </PanelSectionRow>
      {settings?.options.map((option) => {
        const label = LABELS[option.key] || option.key;
        const value = settings.values[option.key];
        return (
          <PanelSectionRow key={option.key}>
            {option.kind === "choice" ? (
              <DropdownItem
                label={label}
                rgOptions={[{ data: "", label: S.DECKY_NOT_SET }, ...option.choices.map((c) => ({ data: c, label: choiceLabel(option.key, c) }))]}
                selectedOption={value}
                onChange={(o) => change(option.key, o.data)}
              />
            ) : option.kind === "toggle" ? (
              <ToggleField label={label} checked={value === true} onChange={(on) => change(option.key, on)} />
            ) : (
              <TextField label={label} value={String(value ?? "")} onChange={(e) => change(option.key, typed(option.kind, e.target.value))} />
            )}
          </PanelSectionRow>
        );
      })}
    </PanelSection>
  );
}

const PARTS = [S.DECKY_PART_UV, S.DECKY_PART_OCR, S.DECKY_PART_CHROMIUM, S.DECKY_PART_YOMITAN];

const tags = (p: Dependency) =>
  [p.optional ? S.DECKY_TAG_OPTIONAL : "", p.present ? S.DECKY_TAG_INSTALLED : ""].filter(Boolean).join(", ");

function Content() {
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [line, setLine] = useState("");
  const wasInstalling = useRef(false);

  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      const status = await installStatus();
      if (stopped) return;
      setInstalling(status.running);
      setLine(status.line);
      if (wasInstalling.current && !status.running) toaster.toast({ title: S.DECKY_NAME, body: status.message });
      wasInstalling.current = status.running;
    };
    poll();
    const timer = setInterval(poll, 2000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, []);

  const run = async (action: () => Promise<Answer>) => {
    setBusy(true);
    try {
      const answer = await action();
      toaster.toast({ title: S.DECKY_NAME, body: answer.message });
    } catch (e) {
      toaster.toast({ title: S.DECKY_NAME, body: S.DECKY_WENT_WRONG.replace("{error}", String(e)) });
    } finally {
      setBusy(false);
    }
  };

  const askInstall = async () => {
    const deps = await getDependencies();
    if (!deps.ok) {
      toaster.toast({ title: S.DECKY_NAME, body: deps.message });
      return;
    }
    showModal(
      <ConfirmModal
        strTitle={S.DECKY_INSTALL_CONFIRM_TITLE}
        strDescription={
          <div>
            <ul style={{ margin: "8px 0", paddingLeft: "20px" }}>
              {deps.packages.map((p) => (
                <li key={p.name}>{tags(p) ? `${p.name} (${tags(p)})` : p.name}</li>
              ))}
              {PARTS.map((part) => (
                <li key={part}>{part}</li>
              ))}
            </ul>
          </div>
        }
        strOKButtonText={S.DECKY_INSTALL_CONFIRM_OK}
        strCancelButtonText={S.DECKY_INSTALL_CONFIRM_CANCEL}
        onOK={() => run(installDependencies)}
      />,
    );
  };

  if (advanced) return <Advanced onBack={() => setAdvanced(false)} />;

  return (
    <PanelSection>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy || installing} onClick={() => run(launch)}>
          {S.DECKY_LAUNCH}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={() => run(stop)}>
          {S.DECKY_STOP}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={busy || installing}
          description={installing ? S.DECKY_INSTALLING.replace("{line}", line) : undefined}
          onClick={askInstall}
        >
          {S.DECKY_INSTALL_DEPENDENCIES}
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => setAdvanced(true)}>
          {S.DECKY_ADVANCED}
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

export default definePlugin(() => ({
  name: S.DECKY_NAME,
  titleView: <div className={staticClasses.Title}>{S.DECKY_NAME}</div>,
  content: <Content />,
  icon: <FaLanguage />,
  onDismount() {},
}));
