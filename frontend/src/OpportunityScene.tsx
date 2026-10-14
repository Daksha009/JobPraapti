import { BriefcaseBusiness, Check, Sparkles, ArrowUpRight } from "lucide-react";
export function OpportunityScene() {
  return (
    <div
      className="opportunity-scene"
      aria-hidden="true"
      onPointerMove={(e) => {
        if (window.matchMedia("(prefers-reduced-motion: reduce)").matches)
          return;
        const rect = e.currentTarget.getBoundingClientRect();
        e.currentTarget.style.setProperty(
          "--tilt-x",
          `${(e.clientY - rect.top - rect.height / 2) / -22}deg`,
        );
        e.currentTarget.style.setProperty(
          "--tilt-y",
          `${(e.clientX - rect.left - rect.width / 2) / 22}deg`,
        );
      }}
      onPointerLeave={(e) => {
        e.currentTarget.style.setProperty("--tilt-x", "0deg");
        e.currentTarget.style.setProperty("--tilt-y", "0deg");
      }}
    >
      <div className="scene-grid" />
      <div className="scene-world">
        <div className="scene-orbit orbit-a" />
        <div className="scene-orbit orbit-b" />
        <div className="scene-core">
          <Sparkles size={54} strokeWidth={1} />
        </div>
        <div className="scene-document">
          <span className="document-icon">
            <BriefcaseBusiness size={23} />
          </span>
          <small>YOUR NEXT CHAPTER</small>
          <strong>
            Opportunity
            <br />
            looks good on you.
          </strong>
          <i />
          <i />
          <i />
          <span className="document-footer">
            Make your move <ArrowUpRight size={16} />
          </span>
        </div>
        <div className="scene-chip">
          <span>
            <Check size={17} />
          </span>{" "}
          More possibility.
        </div>
        <div className="scene-spark spark-a">✦</div>
        <div className="scene-spark spark-b">✦</div>
      </div>
      <span className="scene-caption">
        A LITTLE FOCUS. A WORLD OF POTENTIAL.
      </span>
    </div>
  );
}
