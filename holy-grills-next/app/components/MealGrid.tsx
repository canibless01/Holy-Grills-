import Image from 'next/image';
import {APP_CONFIG,money} from '@/lib/config';
import {imageSize,type Meal} from '@/lib/public-model';
export default function MealGrid({items}:{items:Meal[]}) {
  return <div className="meal-grid">{items.map((meal,index)=><article className="meal" key={meal.id}>
    <div className="meal-photo">{meal.image?<Image src={imageSize(meal.image,800)} alt={meal.name} fill sizes="(max-width: 640px) 92vw, (max-width: 1000px) 45vw, 360px" unoptimized loading={index<3?'eager':'lazy'} />:<span>Photo coming soon</span>}
      {!meal.available?<span className="sold-out">Sold out</span>:null}</div>
    <div className="meal-copy"><h3>{meal.name}</h3><p>{meal.description.split('\n')[0]}</p>
      <div className="meal-bottom"><strong>{money(meal.price)}</strong>{meal.available?<a className="button small" href={`${APP_CONFIG.liveOrigin}/menu/${encodeURIComponent(meal.id)}`}>Choose options <span aria-hidden="true">→</span></a>:<span className="unavailable">Unavailable</span>}</div>
    </div>
  </article>)}</div>;
}
